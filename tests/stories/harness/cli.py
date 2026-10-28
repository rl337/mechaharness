"""Story harness: CLI YAML scenarios drive the product CliInstrumentor."""

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
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from mechaharness.inference.systemone import SystemOneJudgeProvider
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.cli_probes.config import TestHarnessCliConfig
from tests.stories.scenarios.cli_scenario import (
    CliScenario,
    HostInitBlock,
    load_cli_scenario,
    run_cli_scenario,
)


class CliHarness:
    """Intention-blind: load scenarios/*.yaml, run CLI instrumentor, hard-assert."""

    name = "cli"

    def known_ops(self) -> frozenset[str]:
        return frozenset()

    async def run(self, case: StoryCase, backend: StoryBackend) -> None:
        path = case.scenario_path()
        if path is None or not path.is_file():
            raise AssertionError(f"{case.label}: missing CLI scenario YAML")
        scenario = load_cli_scenario(path)
        config = self._build_config(case, backend, scenario)
        instrumentor = get_injector(config).inject(CliInstrumentor)
        # Recipe bind files live under the story/twin root or suite assets/.
        instrumentor.bind_base_dir = case.asset_root()
        assertions = resolve_cli_assertions(config)
        result = await run_cli_scenario(scenario, instrumentor)
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
        scenario: CliScenario,
    ) -> TestHarnessCliConfig:
        response_path = case.path("response.json")
        response: dict = {}
        if response_path.is_file():
            response = case.load_json("response.json")
        model = (
            os.environ.get("MECHA_MODEL", "").strip()
            or str(response.get("model") or "")
            or case.model
        )
        clock = MockDateTimeService(
            datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        )
        host = scenario.host or HostInitBlock()
        needs_judge = any(cmd.verb == "judge_route" for cmd in scenario.commands)
        loop_family, scripted_tool_name = self._tool_loop_needs(scenario, host)

        judge_provider: JudgeProvider | None = None
        if needs_judge:
            judge_provider = self._build_judge_provider(case, backend, response)

        completer_backend = host.backend
        if case.adapter == "openai_compat":
            completer_backend = "openai_compat"
        elif case.adapter == "systemone":
            completer_backend = "systemone"

        if completer_backend == "anthropic":
            return self._anthropic_config(
                case,
                backend,
                response,
                clock,
                model=model,
                harness_family=host.family,
                judge_provider=judge_provider,
            )

        if completer_backend == "openai_compat" or case.adapter == "openai_compat":
            return self._openai_compat_config(
                case,
                backend,
                response,
                clock,
                model=model,
                harness_family=host.family,
                judge_provider=judge_provider,
            )

        if case.adapter == "systemone":
            return TestHarnessCliConfig(
                MockInferenceStrategy(),
                clock,
                model=model,
                judge_provider=judge_provider
                or self._build_judge_provider(case, backend, response),
                harness_family=host.family,
            )

        if case.adapter != "in_process" and completer_backend == "mock":
            raise AssertionError(
                f"{case.label}: unsupported adapter {case.adapter!r} for kind=cli"
            )

        completer = self._scripted_completer(
            response,
            tool_name=scripted_tool_name,
            family=loop_family or host.family,
        )
        return TestHarnessCliConfig(
            completer,
            clock,
            model=model,
            judge_provider=judge_provider,
            harness_family=host.family,
        )

    def _tool_loop_needs(
        self, scenario: CliScenario, host: HostInitBlock
    ) -> tuple[str | None, str | None]:
        for cmd in scenario.commands:
            if cmd.verb != "tool_loop":
                continue
            family = str(cmd.params.get("family") or host.family or "tool_loop")
            tool_name = str(cmd.params.get("tool_name") or "lookup")
            return family, tool_name
        for cmd in scenario.commands:
            if (
                cmd.verb == "run_recipe"
                and cmd.params.get("name") == "conversational_tool_loop"
            ):
                return "tool_loop", str(cmd.params.get("tool_name") or "lookup")
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
        case: StoryCase,
        backend: StoryBackend,
        response: dict,
        clock: MockDateTimeService,
        *,
        model: str,
        harness_family: str,
        judge_provider: JudgeProvider | None,
    ) -> TestHarnessCliConfig:
        settings = Settings(
            inference_backend="openai_compat",
            harness_family=harness_family,
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
            judge_provider=judge_provider,
            harness_family=harness_family,
        )

    def _anthropic_config(
        self,
        case: StoryCase,
        backend: StoryBackend,
        response: dict,
        clock: MockDateTimeService,
        *,
        model: str,
        harness_family: str,
        judge_provider: JudgeProvider | None,
    ) -> TestHarnessCliConfig:
        del case
        settings = Settings(
            inference_backend="anthropic",
            harness_family=harness_family,
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
            judge_provider=judge_provider,
            harness_family=harness_family,
        )

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
            f"{case.label}: judge_route unsupported adapter {case.adapter!r}"
        )
