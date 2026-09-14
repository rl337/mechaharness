"""Live pass-through against a local Qwen OpenAI-compat server.

Skipped unless ``MECHA_LIVE_QWEN=1``. Point ``MECHA_BASE_URL`` and
``MECHA_MODEL`` at the running model (default: LM Studio serving
``qwen/qwen3.6-35b-a3b`` on ``http://127.0.0.1:1234/v1``).
"""

from __future__ import annotations

import os

import pytest

from mechaharness.config import Settings
from mechaharness.core.events import Cost, Inference, InMemoryEventLog
from mechaharness.core.exceptions import InferenceError
from mechaharness.harness.base import HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.openai_compat import OpenAICompatStrategy

LIVE = os.environ.get("MECHA_LIVE_QWEN") == "1"


@pytest.mark.live_qwen
@pytest.mark.skipif(not LIVE, reason="set MECHA_LIVE_QWEN=1 to hit a local Qwen server")
@pytest.mark.asyncio
async def test_pass_through_local_qwen_emits_events_and_cost() -> None:
    settings = Settings(
        inference_backend="lmstudio",
        harness_family="pass_through",
        model=os.environ.get("MECHA_MODEL", "qwen/qwen3.6-35b-a3b"),
        base_url=os.environ.get("MECHA_BASE_URL", "http://127.0.0.1:1234/v1"),
        api_key=os.environ.get("MECHA_API_KEY", "lm-studio"),
        max_tokens=int(os.environ.get("MECHA_MAX_TOKENS", "256")),
    )
    log = InMemoryEventLog()
    strategy = OpenAICompatStrategy(settings, timeout=180.0)
    harness = PassThroughHarness(
        inference=strategy,
        config=HarnessConfig(
            model=settings.model,
            max_turns=1,
            max_tokens=settings.max_tokens,
        ),
        event_log=log,
    )
    try:
        result = await harness.run("Reply with the single word ok.")
    except InferenceError as exc:
        pytest.fail(f"local Qwen is unreachable: {exc}")
    finally:
        await strategy.aclose()

    assert result.final_text
    assert result.turns == 1
    assert result.cost.units >= 1
    types = [event.type for event in result.events]
    assert Cost.key() in types
    assert Inference.key() in types
    inference = log.query(types=[Inference], run_id=result.events[0].run_id)
    assert inference[0].payload.get("content")
