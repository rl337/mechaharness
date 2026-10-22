"""Story harness: persona-task YAML drives product CliInstrumentor verbs."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyiv.files import RealFilesystem
from pyiv.http import AsyncUrllibHttpClient, MemoryAsyncHttpClient
from pyiv.process import OsEnvironment
from pyiv.time import MockDateTimeService

from mechaharness.api_connection import SimpleHttpConnectionConfig
from mechaharness.cli_assertion import resolve_cli_assertions
from mechaharness.cli_instrumentor import CliInstrumentor
from mechaharness.config import Settings
from mechaharness.core.types import ChatMessage, Role, ToolCall, Usage
from mechaharness.di import get_injector
from mechaharness.generator_local_work import (
    GeneratorLocalWork,
    PlanClassifyLocalWork,
    ProjectCodingLocalWork,
)
from mechaharness.inference.anthropic import AnthropicStrategy
from mechaharness.inference.judge import FixtureJudgeProvider, JudgeProvider
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from mechaharness.inference.systemone import SystemOneJudgeProvider
from mechaharness.project_coding_tools import WorkspacePaths, build_coding_tool_registry
from mechaharness.tools.base import ToolRegistry
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.cli_probes.config import TestHarnessCliConfig
from tests.stories.scenarios.user_story_scenario import (
    CodingWriteBlock,
    EnvironmentBlock,
    UserStoryScenario,
    load_user_story_scenario,
    run_user_story_scenario,
)


def _parse_clock(iso: str | None) -> MockDateTimeService:
    if iso:
        raw = iso.replace("Z", "+00:00")
        return MockDateTimeService(datetime.fromisoformat(raw))
    return MockDateTimeService(
        datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    )


class UserStoryHarness:
    """Load scenarios/*.yaml as UserStoryScenario; Config from environment only."""

    name = "user_story"

    def known_ops(self) -> frozenset[str]:
        return frozenset()

    async def run(self, case: StoryCase, backend: StoryBackend) -> None:
        path = case.scenario_path()
        if path is None or not path.is_file():
            raise AssertionError(f"{case.label}: missing user_story scenario YAML")
        scenario = load_user_story_scenario(path)
        config = self._build_config(case, backend, scenario)
        instrumentor = get_injector(config).inject(CliInstrumentor)
        instrumentor.bind_base_dir = path.parent.parent
        assertions = resolve_cli_assertions(config)
        result = await run_user_story_scenario(scenario, instrumentor)
        scenario.assert_expect(
            result,
            assertions,
            label=case.label,
            relax_cassette_exact=backend.mode == "live",
        )

    def _build_config(
        self,
        case: StoryCase,
        backend: StoryBackend,
        scenario: UserStoryScenario,
    ) -> TestHarnessCliConfig:
        env = scenario.environment
        response: dict = {}
        scenario_path = case.scenario_path()
        if scenario_path is not None:
            per_scenario = scenario_path.with_suffix(".response.json")
            if per_scenario.is_file():
                response = json.loads(per_scenario.read_text(encoding="utf-8"))
        if not response:
            response_path = case.path("response.json")
            if response_path.is_file():
                response = case.load_json("response.json")
        model = (
            os.environ.get("MECHA_MODEL", "").strip()
            or str(response.get("model") or "")
            or case.model
        )
        clock = _parse_clock(env.clock)
        loop_family, tool_name = self._tool_loop_needs(scenario, env)
        needs_judge = any(
            next(iter(s.do)) in {"judge", "judge_route"} for s in scenario.steps
        )
        judge_provider: JudgeProvider | None = None
        if needs_judge:
            judge_provider = self._build_judge_provider(case, backend, response)
        rag_retriever = self._build_rag_retriever(case, scenario)
        lifecycle_extensions = self._build_lifecycle_extensions(scenario)

        access_kw = self._access_budget_kwargs(env)
        workspace_root = self._resolve_workspace(env, scenario_path)
        access_kw.update(self._local_work_kwargs(env, workspace_root))
        if env.backend == "anthropic":
            return self._anthropic_config(
                backend,
                response,
                clock,
                model=model,
                family=env.family,
                judge_provider=judge_provider,
                rag_retriever=rag_retriever,
                access_kw=access_kw,
            )
        if env.backend == "openai_compat" or (
            backend.mode == "live"
            and env.backend == "mock"
            and any(next(iter(s.do)) == "infer" for s in scenario.steps)
        ):
            # Live upgrades scripted mock infer walks onto the real reason lane.
            return self._openai_compat_config(
                backend,
                response,
                clock,
                model=model if env.backend == "openai_compat" else (
                    os.environ.get("MECHA_MODEL", "").strip() or model
                ),
                family=env.family,
                judge_provider=judge_provider,
                rag_retriever=rag_retriever,
                access_kw=access_kw,
            )
        if env.backend != "mock":
            raise AssertionError(
                f"{case.label}: unsupported environment.backend {env.backend!r}"
            )

        completer = self._scripted_completer(
            response,
            tool_name=tool_name,
            family=loop_family or env.family,
        )
        return TestHarnessCliConfig(
            completer,
            clock,
            model=model,
            harness_family=env.family,
            judge_provider=judge_provider,
            rag_retriever=rag_retriever,
            lifecycle_extensions=lifecycle_extensions,
            **access_kw,
        )

    def _resolve_workspace(
        self,
        env: EnvironmentBlock,
        scenario_path: Path | None,
    ) -> Path | None:
        raw = env.workspace
        if raw is None:
            return None
        if raw == "temp":
            return Path(tempfile.mkdtemp(prefix="mecha-story-ws-"))
        path = Path(raw).expanduser()
        if path.is_absolute():
            return path.resolve()
        base = scenario_path.parent if scenario_path is not None else Path.cwd()
        return (base / path).resolve()

    def _local_work_kwargs(
        self,
        env: EnvironmentBlock,
        workspace_root: Path | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if workspace_root is not None:
            kwargs["workspace_root"] = workspace_root
        if env.local_work == "plan_classify":
            kwargs["generator_local_work"] = PlanClassifyLocalWork
        elif env.local_work == "project_coding":
            if workspace_root is None:
                raise AssertionError(
                    "environment.local_work=project_coding requires environment.workspace"
                )
            kwargs["generator_local_work"] = self._project_coding_local_work(
                workspace_root, env.coding_write
            )
        return kwargs

    def _project_coding_local_work(
        self,
        workspace_root: Path,
        coding_write: CodingWriteBlock | None,
    ) -> GeneratorLocalWork:
        tools = build_coding_tool_registry(
            workspace=WorkspacePaths(workspace_root),
            filesystem=RealFilesystem(),
        )
        if coding_write is not None:
            complete = _coding_write_stub(tools, coding_write)
        else:
            from mechaharness.project_coding import _offline_stub_complete

            complete = _offline_stub_complete(tools)
        return ProjectCodingLocalWork(
            tools=tools,
            complete=complete,
            workspace_root=workspace_root,
        )

    def _access_budget_kwargs(self, env: EnvironmentBlock) -> dict:
        from mechaharness.host_run_policies import (
            access_policy_from_mapping,
            budget_policy_from_mapping,
            capability_envelope_from_mapping,
        )
        from mechaharness.job_lane_broker import job_lane_broker_from_mapping

        kwargs: dict = {}
        if env.access_policy is not None:
            kwargs["access_policy"] = access_policy_from_mapping(env.access_policy)
        elif env.grants is not None:
            kwargs["grants"] = list(env.grants)
        envelope = capability_envelope_from_mapping(
            env.capability_envelope,
            grants=env.grants,
            authorization_epoch=env.authorization_epoch,
        )
        if envelope is not None:
            kwargs["capability_envelope"] = envelope
        budget = budget_policy_from_mapping(env.budget)
        if budget is not None:
            kwargs["budget_policy"] = budget
        if env.job_lanes is not None or env.lane_grants is not None:
            kwargs["job_lane_broker"] = job_lane_broker_from_mapping(
                env.job_lanes,
                env.lane_grants,
            )
        return kwargs

    def _build_judge_provider(
        self,
        case: StoryCase,
        backend: StoryBackend,
        response: dict,
    ) -> JudgeProvider:
        if backend.mode == "live":
            if not os.environ.get("MECHA_JUDGE_BASE_URL") and not os.environ.get(
                "MECHA_JUDGE_URL"
            ):
                raise AssertionError(
                    "MECHA_JUDGE_BASE_URL (or MECHA_JUDGE_URL) is required "
                    "for live judge stories"
                )
            return SystemOneJudgeProvider(
                connection=SimpleHttpConnectionConfig.for_judge(env=OsEnvironment()),
                client=AsyncUrllibHttpClient(timeout=180.0),
            )
        if case.adapter == "in_process":
            return FixtureJudgeProvider(response.get("answers") or {})
        if case.adapter == "systemone":
            connection = SimpleHttpConnectionConfig(
                base_url="http://story.invalid",
                path="/v1/systemone",
                model="laya",
            )
            client = MemoryAsyncHttpClient()
            client.add("POST", connection.endpoint_url(), json=response)
            return SystemOneJudgeProvider(connection=connection, client=client)
        raise AssertionError(
            f"{case.label}: judge unsupported adapter {case.adapter!r}"
        )

    def _build_rag_retriever(
        self,
        case: StoryCase,
        scenario: UserStoryScenario,
    ):
        from pathlib import Path

        import yaml

        from mechaharness.rag import FixtureRagRetriever

        corpus = scenario.environment.rag_corpus
        if not corpus:
            return None
        path = case.path(corpus)
        if not Path(path).is_file():
            raise AssertionError(f"{case.label}: missing rag_corpus {corpus}")
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict) and "candidates" in raw:
            candidates = list(raw["candidates"])
        elif isinstance(raw, list):
            candidates = raw
        else:
            raise AssertionError(
                f"{case.label}: rag_corpus must be a candidate list or "
                "{candidates: [...]}"
            )
        return FixtureRagRetriever(candidates)

    def _build_lifecycle_extensions(
        self,
        scenario: UserStoryScenario,
    ) -> dict[str, object]:
        from tests.stories.hosts.lifecycle_extensions import STORY_LIFECYCLE_EXTENSIONS

        out: dict[str, object] = {}
        for eid in scenario.environment.lifecycle_extensions:
            cls = STORY_LIFECYCLE_EXTENSIONS.get(eid)
            if cls is None:
                raise AssertionError(
                    f"unknown lifecycle extension {eid!r}; "
                    f"known: {sorted(STORY_LIFECYCLE_EXTENSIONS)}"
                )
            out[eid] = cls()
        return out

    def _tool_loop_needs(
        self, scenario: UserStoryScenario, env: EnvironmentBlock
    ) -> tuple[str | None, str | None]:
        for step in scenario.steps:
            verb = next(iter(step.do))
            params = step.do[verb] or {}
            if not isinstance(params, dict):
                continue
            if verb == "tool_loop":
                family = str(params.get("family") or env.family or "tool_loop")
                return family, str(params.get("tool_name") or "lookup")
            if verb == "run_recipe" and params.get("name") == "conversational_tool_loop":
                return "tool_loop", str(params.get("tool_name") or "lookup")
        return None, None

    def _scripted_completer(
        self,
        response: dict,
        *,
        tool_name: str | None,
        family: str,
    ) -> ScriptedInference:
        if family == "react" and tool_name is not None:
            return ScriptedInference(
                [
                    ChatMessage(
                        role=Role.ASSISTANT,
                        content=(
                            f"Thought: use the tool\n"
                            f"Action: {tool_name}\n"
                            f"Action Input: {{}}\n"
                        ),
                    ),
                    ChatMessage(
                        role=Role.ASSISTANT,
                        content="Thought: done\nFinal Answer: done\n",
                    ),
                ]
            )
        if tool_name is not None:
            return ScriptedInference(
                [
                    ChatMessage(
                        role=Role.ASSISTANT,
                        content=None,
                        tool_calls=[
                            ToolCall(
                                id="c1",
                                name=tool_name,
                                arguments={},
                            )
                        ],
                    ),
                    ChatMessage(role=Role.ASSISTANT, content="done"),
                ]
            )
        content = str(response.get("content") or "ok")
        usage_raw = response.get("usage") or {}
        if usage_raw:
            usage = Usage(
                prompt_tokens=usage_raw.get("prompt_tokens"),
                completion_tokens=usage_raw.get("completion_tokens"),
                total_tokens=usage_raw.get("total_tokens"),
            )
        else:
            usage = Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        return ScriptedInference(
            [ChatMessage(role=Role.ASSISTANT, content=content)],
            usages=[usage],
        )

    def _openai_compat_config(
        self,
        backend: StoryBackend,
        response: dict,
        clock: MockDateTimeService,
        *,
        model: str,
        family: str,
        judge_provider: JudgeProvider | None = None,
        rag_retriever: object | None = None,
        access_kw: dict | None = None,
    ) -> TestHarnessCliConfig:
        from mechaharness.rag import RagRetriever

        settings = Settings(
            inference_backend="openai_compat",
            harness_family=family,
            model=model,
            base_url=os.environ.get("MECHA_BASE_URL", "http://story.invalid/v1"),
            api_key=os.environ.get("MECHA_API_KEY", "story"),
            max_tokens=int(os.environ.get("MECHA_MAX_TOKENS", "256")),
        )
        base = (settings.base_url or "http://story.invalid/v1").rstrip("/")
        if backend.mode == "static":
            client = MemoryAsyncHttpClient()
            client.add("POST", f"{base}/chat/completions", json=response)
        else:
            if not os.environ.get("MECHA_BASE_URL"):
                raise AssertionError(
                    "MECHA_BASE_URL is required for live openai_compat stories"
                )
            client = AsyncUrllibHttpClient(timeout=180.0)
        strategy = OpenAICompatStrategy(settings, client=client, timeout=180.0)
        return TestHarnessCliConfig(
            strategy,
            clock,
            model=model,
            harness_family=family,
            judge_provider=judge_provider,
            rag_retriever=rag_retriever if isinstance(rag_retriever, RagRetriever) else None,
            **(access_kw or {}),
        )

    def _anthropic_config(
        self,
        backend: StoryBackend,
        response: dict,
        clock: MockDateTimeService,
        *,
        model: str,
        family: str,
        judge_provider: JudgeProvider | None = None,
        rag_retriever: object | None = None,
        access_kw: dict | None = None,
    ) -> TestHarnessCliConfig:
        from mechaharness.rag import RagRetriever

        settings = Settings(
            inference_backend="anthropic",
            harness_family=family,
            model=model or "claude-story",
            base_url=os.environ.get("MECHA_BASE_URL", "http://story.invalid"),
            api_key=os.environ.get("MECHA_API_KEY", "story"),
            max_tokens=int(os.environ.get("MECHA_MAX_TOKENS", "256")),
        )
        base = (settings.base_url or "http://story.invalid").rstrip("/")
        if backend.mode == "static":
            client = MemoryAsyncHttpClient()
            client.add("POST", f"{base}/v1/messages", json=response)
        else:
            if not os.environ.get("MECHA_BASE_URL"):
                raise AssertionError(
                    "MECHA_BASE_URL is required for live anthropic stories"
                )
            client = AsyncUrllibHttpClient(timeout=180.0)
        strategy = AnthropicStrategy(settings, client=client, timeout=180.0)
        return TestHarnessCliConfig(
            strategy,
            clock,
            model=settings.model,
            harness_family=family,
            judge_provider=judge_provider,
            rag_retriever=rag_retriever if isinstance(rag_retriever, RagRetriever) else None,
            **(access_kw or {}),
        )


def _coding_write_stub(
    tools: ToolRegistry,
    coding_write: CodingWriteBlock,
) -> Any:
    """Deterministic Completer that writes one workspace file then finishes."""

    state = {"wrote": False}
    path = coding_write.path
    content = coding_write.content

    def complete(messages: object, meta: object = None) -> dict[str, Any]:
        del messages, meta
        if not state["wrote"] and "write_file" in tools:
            state["wrote"] = True
            # Ensure package imports work for helpers/foo.py style paths.
            parts = Path(path).parts
            if len(parts) > 1:
                pkg = Path(parts[0])
                init_rel = str(pkg / "__init__.py")
                if "write_file" in tools:
                    tools.get("write_file").handler(path=init_rel, content="")
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_write",
                        "function": {
                            "name": "write_file",
                            "arguments": {"path": path, "content": content},
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "done", "tool_calls": []}

    return complete
