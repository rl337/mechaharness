"""Token usage on cost ledger and reasoning_content passthrough."""

from __future__ import annotations

import pytest

from mechaharness.core.events import Cost, Inference, InMemoryEventLog
from mechaharness.core.types import ChatMessage, Role, Usage
from mechaharness.harness.base import HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from tests.fakes import ScriptedInference


@pytest.mark.asyncio
async def test_pass_through_records_usage_on_cost() -> None:
    log = InMemoryEventLog()
    inference = ScriptedInference(
        [ChatMessage(role=Role.ASSISTANT, content="ok", reasoning_content="think")],
        usages=[Usage(prompt_tokens=10, completion_tokens=4, total_tokens=14)],
    )
    harness = PassThroughHarness(
        inference=inference,
        config=HarnessConfig(model="m"),
        event_log=log,
    )
    result = await harness.run("hi")
    assert result.final_text == "ok"
    assert result.cost.units == 1
    assert result.cost.prompt_tokens == 10
    assert result.cost.completion_tokens == 4
    assert result.cost.total_tokens == 14
    entry = result.cost.entries[0]
    assert entry.prompt_tokens == 10
    assert entry.total_tokens == 14
    cost_events = log.query(types=[Cost], run_id=result.events[0].run_id)
    assert cost_events[0].payload["total_tokens"] == 14
    inference_events = log.query(types=[Inference], run_id=result.events[0].run_id)
    assert inference_events[0].payload["reasoning_content"] == "think"
    assert inference_events[0].payload["usage"]["total_tokens"] == 14
    assert result.messages[-1].reasoning_content == "think"
