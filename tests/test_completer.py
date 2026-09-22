"""Completer ABC and nested harness as sub-agent."""

from __future__ import annotations

import pytest

from mechaharness.core.completer import Completer
from mechaharness.core.events import AgentStart, InMemoryEventLog
from mechaharness.core.types import ChatMessage, CompletionRequest, Role
from mechaharness.harness.base import HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from tests.fakes import ScriptedInference


@pytest.mark.asyncio
async def test_harness_is_a_completer() -> None:
    inference = ScriptedInference([ChatMessage(role=Role.ASSISTANT, content="pong")])
    harness = PassThroughHarness(
        inference=inference,
        config=HarnessConfig(model="m"),
    )
    assert isinstance(harness, Completer)
    assert isinstance(inference, Completer)
    assert isinstance(inference, InferenceStrategy)
    response = await harness.complete(
        CompletionRequest(
            model="m",
            messages=[ChatMessage(role=Role.USER, content="ping")],
        )
    )
    assert response.message.content == "pong"
    assert response.cost is not None
    assert response.cost.units >= 1


@pytest.mark.asyncio
async def test_nested_harness_shares_event_log() -> None:
    log = InMemoryEventLog()
    child = PassThroughHarness(
        inference=ScriptedInference([ChatMessage(role=Role.ASSISTANT, content="inner")]),
        config=HarnessConfig(model="child"),
        event_log=log,
        agent_id="child-agent",
    )
    parent = PassThroughHarness(
        inference=child,
        config=HarnessConfig(model="parent"),
        event_log=log,
        agent_id="parent-agent",
    )
    result = await parent.run("hello")
    assert result.final_text == "inner"
    assert child.parent_agent_id == "parent-agent"
    children = log.agents(parent_id="parent-agent")
    assert any(ref.agent_id == "child-agent" for ref in children)
    starts = log.query(types=[AgentStart], descendants=True, agent_id="parent-agent")
    assert {event.agent_id for event in starts} >= {"parent-agent", "child-agent"}
