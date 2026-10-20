"""Story harness: persona-task YAML drives product CliInstrumentor verbs."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from pyiv.http import AsyncUrllibHttpClient, MemoryAsyncHttpClient
from pyiv.process import OsEnvironment
from pyiv.time import MockDateTimeService

from mechaharness.api_connection import SimpleHttpConnectionConfig
from mechaharness.cli_assertion import resolve_cli_assertions
from mechaharness.cli_instrumentor import CliInstrumentor
from mechaharness.config import Settings
from mechaharness.core.types import ChatMessage, Role, ToolCall, Usage
from mechaharness.di import get_injector
from mechaharness.inference.anthropic import AnthropicStrategy
from mechaharness.inference.judge import FixtureJudgeProvider, JudgeProvider
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from mechaharness.inference.systemone import SystemOneJudgeProvider
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.cli_probes.config import TestHarnessCliConfig
from tests.stories.scenarios.user_story_scenario import (
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
        scenario.assert_expect(result, assertions, label=case.label)

    def _build_config(
        self,
        case: StoryCase,
        backend: StoryBackend,
        scenario: UserStoryScenario,
    ) -> TestHarnessCliConfig:
        env = scenario.environment
        response_path = case.path("response.json")
        response: dict = {}
        if response_path.is_file():
            response = case.load_json("response.json")
        model = (
            os.environ.get("MECHA_MODEL", "").strip()
            or str(response.get("model") or "")
            or case.model
        )
        clock = _parse_clock(env.clock)
        loop_family, tool_name = self._tool_loop_needs(scenario, env)
        needs_judge = any(next(iter(s.do)) == "judge_route" for s in scenario.steps)
        judge_provider: JudgeProvider | None = None
        if needs_judge:
            judge_provider = self._build_judge_provider(case, backend, response)

        if env.backend == "anthropic":
            return self._anthropic_config(
                backend,
                response,
                clock,
                model=model,
                family=env.family,
                judge_provider=judge_provider,
            )
        if env.backend == "openai_compat":
            return self._openai_compat_config(
                backend,
                response,
                clock,
                model=model,
                family=env.family,
                judge_provider=judge_provider,
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
        )

    def _build_judge_provider(
        self,
        case: StoryCase,
        backend: StoryBackend,
        response: dict,
    ) -> JudgeProvider:
        if case.adapter == "in_process":
            return FixtureJudgeProvider(response.get("answers") or {})
        if case.adapter == "systemone":
            if backend.mode == "static":
                connection = SimpleHttpConnectionConfig(
                    base_url="http://story.invalid",
                    path="/v1/systemone",
                    model="laya",
                )
                client = MemoryAsyncHttpClient()
                client.add("POST", connection.endpoint_url(), json=response)
                return SystemOneJudgeProvider(connection=connection, client=client)
            return SystemOneJudgeProvider(
                connection=SimpleHttpConnectionConfig.for_judge(env=OsEnvironment()),
                client=AsyncUrllibHttpClient(),
            )
        raise AssertionError(
            f"{case.label}: judge_route unsupported adapter {case.adapter!r}"
        )

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
    ) -> TestHarnessCliConfig:
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
    ) -> TestHarnessCliConfig:
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
        )
