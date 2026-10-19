"""Story harness: CLI YAML scenarios drive the product CliInstrumentor."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from pyiv.http import AsyncUrllibHttpClient, MemoryAsyncHttpClient
from pyiv.time import MockDateTimeService

from mechaharness.cli_instrumentor import CliInstrumentor
from mechaharness.config import Settings
from mechaharness.core.types import ChatMessage, Role, Usage
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.scenarios.cli_scenario import load_cli_scenario, run_cli_scenario


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
        instrumentor = self._build_instrumentor(case, backend)
        result = await run_cli_scenario(scenario, instrumentor)
        scenario.assert_expect(result, label=case.label)

    def _build_instrumentor(
        self,
        case: StoryCase,
        backend: StoryBackend,
    ) -> CliInstrumentor:
        response_path = case.path("response.json")
        response: dict = {}
        if response_path.is_file():
            response = case.load_json("response.json")
        # Live servers use served ids (e.g. qwen/qwen3.6-35b-a3b); fixture
        # folder names are not wire model ids.
        model = (
            os.environ.get("MECHA_MODEL", "").strip()
            or str(response.get("model") or "")
            or case.model
        )
        clock = MockDateTimeService(
            datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        )

        if case.adapter == "in_process":
            content = str(response.get("content") or "ok")
            usage_raw = response.get("usage") or {}
            usage = Usage(
                prompt_tokens=usage_raw.get("prompt_tokens"),
                completion_tokens=usage_raw.get("completion_tokens"),
                total_tokens=usage_raw.get("total_tokens"),
            )
            completer = ScriptedInference(
                [ChatMessage(role=Role.ASSISTANT, content=content)],
                usages=[usage],
            )
            return CliInstrumentor(
                completer,
                datetime_service=clock,
                model=model,
            )

        if case.adapter == "openai_compat":
            settings = Settings(
                inference_backend="openai_compat",
                harness_family="pass_through",
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
            return CliInstrumentor(
                strategy,
                datetime_service=clock,
                model=model,
            )

        raise AssertionError(
            f"{case.label}: unsupported adapter {case.adapter!r} for kind=cli"
        )
