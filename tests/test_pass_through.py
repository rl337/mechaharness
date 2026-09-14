"""Pass-through harness: one inference call, EventLog + cost ledger."""

from __future__ import annotations

import pytest
from pyiv import get_injector

from mechaharness.config import Settings
from mechaharness.core.contract import RunRequest
from mechaharness.core.events import (
    AgentEnd,
    AgentStart,
    Cost,
    Inference,
    InMemoryEventLog,
    RunEnd,
    RunStart,
    TurnStart,
)
from mechaharness.core.types import ChatMessage, Role
from mechaharness.di import SettingsConfig, list_harness_families
from mechaharness.factory import run
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.mock import MockInferenceStrategy
from tests.fakes import ScriptedInference

EXPECTED_PASS_THROUGH_TYPES = [
    AgentStart.key(),
    RunStart.key(),
    TurnStart.key(),
    Cost.key(),
    Inference.key(),
    RunEnd.key(),
    AgentEnd.key(),
]


def test_pass_through_is_configured() -> None:
    assert "pass_through" in list_harness_families()


@pytest.mark.asyncio
async def test_pass_through_mock_emits_events_and_cost() -> None:
    log = InMemoryEventLog()
    inference = ScriptedInference(
        [ChatMessage(role=Role.ASSISTANT, content="four")]
    )
    harness = PassThroughHarness(
        inference=inference,
        config=HarnessConfig(model="mock-model"),
        event_log=log,
    )
    result = await harness.run("What is 2+2?")
    assert result.final_text == "four"
    assert result.turns == 1
    assert result.cost.units == 1
    assert result.cost.entries[0].kind == "inference"
    assert result.cost.entries[0].name == "scripted"
    types = [event.type for event in result.events]
    assert types == EXPECTED_PASS_THROUGH_TYPES
    assert log.query(agent_id=harness.agent_id, types=[Cost])[0].payload["units"] == 1


@pytest.mark.asyncio
async def test_pass_through_via_mock_backend() -> None:
    settings = Settings(
        inference_backend="mock",
        harness_family="pass_through",
        model="mock",
    )
    injector = get_injector(SettingsConfig(settings=settings, tools=None))
    harness = injector.inject(AbstractHarness)
    assert isinstance(harness, PassThroughHarness)
    result = await harness.run("hello")
    assert result.final_text == "mock reply: hello"
    assert [event.type for event in result.events] == EXPECTED_PASS_THROUGH_TYPES
    assert result.cost.units == 1


@pytest.mark.asyncio
async def test_factory_run_mock_pass_through() -> None:
    response = await run(
        RunRequest(
            prompt="ping",
            backend="mock",
            family="pass_through",
            model="mock",
        )
    )
    assert response.final_text == "mock reply: ping"
    assert response.turns == 1
    types = [item["type"] for item in response.events]
    assert types == EXPECTED_PASS_THROUGH_TYPES


def test_mock_strategy_describe() -> None:
    meta = MockInferenceStrategy().describe()
    assert meta["name"] == "mock"
    assert meta["network"] is False
