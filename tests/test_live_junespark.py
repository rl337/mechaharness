"""Live pass-through against the ``junespark`` OpenAI-compat backend.

Skipped unless ``MECHA_LIVE_JUNESPARK=1``. Set ``MECHA_BASE_URL`` and
``MECHA_MODEL`` to the running server's served model id.
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

LIVE = os.environ.get("MECHA_LIVE_JUNESPARK") == "1"


@pytest.mark.live_junespark
@pytest.mark.skipif(not LIVE, reason="set MECHA_LIVE_JUNESPARK=1 to hit junespark")
@pytest.mark.asyncio
async def test_pass_through_junespark_emits_events_and_usage() -> None:
    settings = Settings(
        inference_backend="junespark",
        harness_family="pass_through",
        model=os.environ.get("MECHA_MODEL", "qwen3-30b-thinking"),
        base_url=os.environ.get("MECHA_BASE_URL", "http://192.168.1.21:8000/v1"),
        api_key=os.environ.get("MECHA_API_KEY", "junespark"),
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
        pytest.fail(f"junespark is unreachable: {exc}")
    finally:
        await strategy.aclose()

    assert result.final_text
    assert result.turns == 1
    assert result.cost.units >= 1
    types = [event.type for event in result.events]
    assert Cost.key() in types
    assert Inference.key() in types
