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

    async def run(
        self,
        case: StoryCase,
        backend: StoryBackend,
        *,
        suite_workspace: Path | None = None,
    ) -> None:
        path = case.scenario_path()
        if path is None or not path.is_file():
            raise AssertionError(f"{case.label}: missing user_story scenario YAML")
        scenario = load_user_story_scenario(path)
        config = self._build_config(
            case, backend, scenario, suite_workspace=suite_workspace
        )
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
        *,
        suite_workspace: Path | None = None,
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
        workspace_root = self._resolve_workspace(
            env, scenario_path, suite_workspace=suite_workspace
        )
        live_model = (
            os.environ.get("MECHA_MODEL", "").strip()
            or model
        )
        access_kw.update(
            self._local_work_kwargs(
                env,
                workspace_root,
                backend=backend,
                model=live_model,
            )
        )
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
        *,
        suite_workspace: Path | None = None,
    ) -> Path | None:
        raw = env.workspace
        if raw is None:
            return None
        if raw == "suite":
            if suite_workspace is None:
                raise AssertionError(
                    "environment.workspace=suite requires a sequential suite "
                    "workspace (run via test_user_story_suite)"
                )
            return suite_workspace.resolve()
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
        *,
        backend: StoryBackend,
        model: str,
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
            writes = list(env.coding_writes or [])
            if not writes and env.coding_write is not None:
                writes = [env.coding_write]
            if env.git_seed == "feature_branch":
                _seed_feature_branch_git_repo(workspace_root)
            if env.ci_seed == "failing_check":
                _seed_failing_ci_check(workspace_root)
            if env.write_guard_seed == "healthy_module":
                _seed_healthy_module_for_write_guard(workspace_root)
            kwargs["generator_local_work"] = self._project_coding_local_work(
                workspace_root,
                writes,
                backend=backend,
                model=model,
                coding_git=env.coding_git,
                coding_github=env.coding_github,
                coding_tool_script=env.coding_tool_script,
            )
        return kwargs

    def _project_coding_local_work(
        self,
        workspace_root: Path,
        coding_writes: list[CodingWriteBlock],
        *,
        backend: StoryBackend,
        model: str,
        coding_git: str | None = None,
        coding_github: str | None = None,
        coding_tool_script: str | None = None,
    ) -> GeneratorLocalWork:
        from mechaharness.coding_git import (
            LocalProcessCodingGit,
            RecordingPullRequestCodingGit,
        )
        from mechaharness.github_client import RecordingGitHubClient
        from mechaharness.github_connection import GitHubConnectionConfig

        local_git = LocalProcessCodingGit(workspace=workspace_root)
        if coding_git == "local_mock_pr":
            bound_git = RecordingPullRequestCodingGit(local_git)
        else:
            bound_git = local_git
        github = None
        github_connection = None
        if coding_github == "local_mock_ci":
            github = RecordingGitHubClient()
            github_connection = GitHubConnectionConfig(
                token="story-mock",
                owner="acme",
                repo="demo",
            )
        tools = build_coding_tool_registry(
            workspace=WorkspacePaths(workspace_root),
            filesystem=RealFilesystem(),
            coding_git=bound_git,
            github=github,
            github_connection=github_connection,
        )
        if backend.mode == "live":
            # Ignore offline stubs; drive tools with a real Completer.
            # Pull requests stay on RecordingPullRequestCodingGit when
            # coding_git=local_mock_pr (no forge).
            complete = self._live_coding_complete(tools, model=model)
            max_iterations = int(os.environ.get("MECHA_CODING_MAX_ITERATIONS", "24"))
        elif coding_tool_script:
            steps = _coding_tool_script_steps(coding_tool_script)
            complete = _coding_tool_script_stub(steps)
            max_iterations = max(8, len(steps) + 2)
        elif coding_writes:
            complete = _coding_writes_stub(tools, coding_writes)
            # One tool round per stub file, plus a finish round.
            max_iterations = max(8, len(coding_writes) + 2)
        else:
            from mechaharness.project_coding import _offline_stub_complete

            complete = _offline_stub_complete(tools)
            max_iterations = 8
        return ProjectCodingLocalWork(
            tools=tools,
            complete=complete,
            workspace_root=workspace_root,
            max_iterations=max_iterations,
        )

    def _live_coding_complete(self, tools: ToolRegistry, *, model: str) -> Any:
        """OpenAI-compat Completer adapted for ProjectCodingLocalWork tool loops."""
        from mechaharness.project_coding import completer_as_tool_loop_complete

        if not os.environ.get("MECHA_BASE_URL"):
            raise AssertionError(
                "MECHA_BASE_URL is required for live project_coding stories"
            )
        settings = Settings(
            inference_backend="openai_compat",
            harness_family="pass_through",
            model=model,
            base_url=os.environ.get("MECHA_BASE_URL"),
            api_key=os.environ.get("MECHA_API_KEY", "local"),
            max_tokens=int(os.environ.get("MECHA_MAX_TOKENS", "2048")),
        )
        client = CountingLiveHttpClient(timeout=300.0)
        strategy = OpenAICompatStrategy(settings, client=client, timeout=300.0)
        return completer_as_tool_loop_complete(
            strategy,
            tools=tools,
            model=str(settings.model or model),
            max_tokens=int(settings.max_tokens or 2048),
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


class CountingLiveHttpClient(AsyncUrllibHttpClient):
    """Async HTTP client that counts POSTs for live-inference proof."""

    post_count: int = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        type(self).post_count = 0

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Any = None,
        params: Any = None,
        data: Any = None,
        json: Any = None,
        timeout: float | None = None,
    ) -> Any:
        if str(method).upper() == "POST":
            type(self).post_count += 1
        return await super().request(
            method,
            url,
            headers=headers,
            params=params,
            data=data,
            json=json,
            timeout=timeout,
        )


def reset_live_http_post_count() -> None:
    CountingLiveHttpClient.post_count = 0


def live_http_post_count() -> int:
    return int(CountingLiveHttpClient.post_count)


def _coding_writes_stub(
    tools: ToolRegistry,
    coding_writes: list[CodingWriteBlock],
) -> Any:
    """Deterministic Completer that writes one or more workspace files then finishes."""

    pending = list(coding_writes)
    state = {"i": 0}

    planned_paths = {b.path for b in pending}

    def complete(messages: object, meta: object = None) -> dict[str, Any]:
        del messages, meta
        if state["i"] < len(pending) and "write_file" in tools:
            block = pending[state["i"]]
            state["i"] += 1
            path = block.path
            # Seed empty __init__.py for nested packages when the stub tree
            # did not already include one (single-file helper arcs).
            parts = Path(path).parts
            if len(parts) > 1:
                init_rel = str(Path(parts[0]) / "__init__.py")
                if init_rel not in planned_paths and init_rel != path:
                    try:
                        tools.get("write_file").handler(path=init_rel, content="")
                    except Exception:  # noqa: BLE001
                        pass
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_write_{state['i']}",
                        "function": {
                            "name": "write_file",
                            "arguments": {
                                "path": path,
                                "content": block.content,
                            },
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "done", "tool_calls": []}

    return complete


def _coding_write_stub(
    tools: ToolRegistry,
    coding_write: CodingWriteBlock,
) -> Any:
    """Backward-compatible single-file stub."""
    return _coding_writes_stub(tools, [coding_write])


def _seed_feature_branch_git_repo(root: Path) -> None:
    """Init main + feature branch with one divergent commit (local git only)."""
    import subprocess

    def run(args: list[str]) -> None:
        subprocess.run(args, cwd=str(root), check=True, capture_output=True, text=True)

    run(["git", "init", "-b", "main"])
    run(["git", "config", "user.email", "story@example.com"])
    run(["git", "config", "user.name", "Mecha Story"])
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    run(["git", "add", "README.md"])
    run(["git", "commit", "-m", "init on main"])
    run(["git", "checkout", "-b", "feature"])
    (root / "helper.py").write_text(
        "def answer() -> int:\n    return 42\n", encoding="utf-8"
    )
    run(["git", "add", "helper.py"])
    run(["git", "commit", "-m", "add helper on feature"])


def _seed_healthy_module_for_write_guard(root: Path) -> None:
    """Plant a substantial module that a careless Completer might try to gut."""
    body = (
        '"""Healthy module used to prove CodingWriteGuard refusals."""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n\n\n"
        "@dataclass\n"
        "class WorkspacePaths:\n"
        '    """Resolve paths under a workspace root."""\n\n'
        "    root: str\n\n"
        "    def resolve(self, relative: str) -> str:\n"
        '        return f"{self.root}/{relative}"\n\n\n'
        "def build_coding_tool_registry(*, workspace: WorkspacePaths) -> dict:\n"
        '    """Register confined tools under *workspace*."""\n\n'
        "    def read_file(path: str) -> str:\n"
        '        return f"read:{path}"\n\n'
        "    return {\"read_file\": read_file, \"paths\": workspace}\n\n\n"
        "def helper() -> int:\n"
        "    return 42\n"
    )
    body = body + ("\n# padding for CodingWriteGuard.min_existing_bytes\n" * 20)
    (root / "healthy_module.py").write_text(body, encoding="utf-8")


def _seed_failing_ci_check(root: Path) -> None:
    """Plant a broken module and a fake Actions failure log for CI repair stories."""
    (root / "widget.py").write_text(
        "def answer() -> int:\n    return 'not-an-int'\n",
        encoding="utf-8",
    )
    mech = root / ".mechaharness"
    mech.mkdir(parents=True, exist_ok=True)
    (mech / "ci_failure.log").write_text(
        "\n".join(
            [
                "Job: checks",
                "Step: Run checks",
                "Conclusion: failure",
                "",
                "_________________ ERROR collecting tests/test_widget.py _________________",
                "tests/test_widget.py:3: in <module>",
                "    from widget import answer",
                "E   TypeError: answer() must return int, got str",
                "",
                "Failed: widget.py: answer() returns str instead of int 42",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _coding_tool_script_steps(script_id: str) -> list[dict[str, Any]]:
    """Named offline Completer scripts that exercise CodingGit tools."""
    if script_id == "git_inspect":
        return [
            {"name": "git_status", "arguments": {}},
            {"name": "git_log", "arguments": {"base": "main", "max_count": 10}},
            {
                "name": "git_diff",
                "arguments": {"base": "main", "stat_only": True},
            },
            {
                "name": "write_file",
                "arguments": {
                    "path": ".mechaharness/git_inspect.md",
                    "content": (
                        "# git inspect\n\n"
                        "branch feature vs main\n"
                        "helper.py added\n"
                    ),
                },
            },
            {"finish": True},
        ]
    if script_id == "git_open_pr":
        return [
            {"name": "git_log", "arguments": {"base": "main", "max_count": 10}},
            {
                "name": "git_diff",
                "arguments": {"base": "main", "stat_only": True},
            },
            {
                "name": "create_pull_request",
                "arguments": {
                    "title": "Add helper on feature",
                    "body": (
                        "## Summary\n"
                        "- Add helper.py on the feature branch.\n\n"
                        "## Test plan\n"
                        "- [ ] Local git inspect vs main\n"
                        "- [ ] Mock PR URL recorded\n"
                    ),
                    "base": "main",
                },
            },
            {
                "name": "write_file",
                "arguments": {
                    "path": ".mechaharness/pr_url.txt",
                    "content": "https://example.test/pull/1\n",
                },
            },
            {"finish": True},
        ]
    if script_id == "ci_repair":
        return [
            {
                "name": "read_file",
                "arguments": {"path": ".mechaharness/ci_failure.log"},
            },
            {
                "name": "write_file",
                "arguments": {
                    "path": "widget.py",
                    "content": "def answer() -> int:\n    return 42\n",
                },
            },
            {
                "name": "write_file",
                "arguments": {
                    "path": ".mechaharness/ci_fix.md",
                    "content": (
                        "# CI fix\n\n"
                        "Failed step: Run checks\n"
                        "Changed: widget.py — answer() now returns int 42\n"
                    ),
                },
            },
            {"finish": True},
        ]
    if script_id == "ci_diagnose":
        return [
            {"name": "ci_checks", "arguments": {"ref": "HEAD"}},
            {
                "name": "ci_job_log",
                "arguments": {"job_id": "9001", "max_bytes": 20_000},
            },
            {
                "name": "write_file",
                "arguments": {
                    "path": ".mechaharness/ci_diagnosis.md",
                    "content": (
                        "# CI diagnosis\n\n"
                        "Check: checks — conclusion failure\n"
                        "Job id: 9001\n"
                        "Root cause: Ruff lint failed; Mypy type checking "
                        "failed; Pytest ModuleNotFoundError: No module "
                        "named 'widget'; coverage 77.55% below 78.0%\n"
                    ),
                },
            },
            {"finish": True},
        ]
    if script_id == "write_gutting_attempt":
        gutted = (
            "from mechaharness.github_client import GitHubClient\n\n"
            "def ci_checks(github_client, repo, workflow_id):\n"
            "    return github_client.list_check_runs(repo, workflow_id)\n\n"
            "def build_coding_tool_registry(github_client=None):\n"
            "    return {'ci_checks': ci_checks if github_client else None}\n"
        )
        return [
            {
                "name": "write_file",
                "arguments": {
                    "path": "healthy_module.py",
                    "content": gutted,
                },
            },
            {
                "name": "write_file",
                "arguments": {
                    "path": ".mechaharness/write_guard_note.md",
                    "content": (
                        "# write guard\n\n"
                        "Gutting of healthy_module.py was blocked / refused.\n"
                    ),
                },
            },
            {"finish": True},
        ]
    raise AssertionError(f"unknown coding_tool_script: {script_id!r}")


def _coding_tool_script_stub(steps: list[dict[str, Any]]) -> Any:
    """Deterministic Completer that emits a fixed sequence of tool calls."""

    state = {"i": 0}

    def complete(messages: object, meta: object = None) -> dict[str, Any]:
        del messages, meta
        if state["i"] >= len(steps):
            return {"role": "assistant", "content": "done", "tool_calls": []}
        step = steps[state["i"]]
        state["i"] += 1
        if step.get("finish"):
            return {
                "role": "assistant",
                "content": str(step.get("content") or "done"),
                "tool_calls": [],
            }
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_script_{state['i']}",
                    "function": {
                        "name": str(step["name"]),
                        "arguments": dict(step.get("arguments") or {}),
                    },
                }
            ],
        }

    return complete
