"""Harness loop tests using a scripted inference strategy."""

from __future__ import annotations

import pytest

from mechaharness.core.types import ChatMessage, Role, ToolCall
from mechaharness.di import list_harness_families
from mechaharness.harness.base import HarnessConfig
from mechaharness.harness.families import OpenAIToolsHarness
from mechaharness.harness.react import ReactHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.tools.base import ToolRegistry
from tests.fakes import ScriptedInference


@pytest.fixture
def tools() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(
        description="Add two numbers",
        parameters={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    )
    def add(a: float, b: float) -> str:
        return str(a + b)

    return registry


def test_harness_families_configured() -> None:
    families = list_harness_families()
    assert "tool_loop" in families
    assert "pass_through" in families
    assert "react" in families
    assert "openai_tools" in families


@pytest.mark.asyncio
async def test_tool_loop_executes_then_stops(tools: ToolRegistry) -> None:
    inference = ScriptedInference(
        [
            ChatMessage(
                role=Role.ASSISTANT,
                content=None,
                tool_calls=[ToolCall(id="1", name="add", arguments={"a": 2, "b": 3})],
            ),
            ChatMessage(role=Role.ASSISTANT, content="The sum is 5."),
        ]
    )
    harness = ToolLoopHarness(
        inference=inference,
        tools=tools,
        config=HarnessConfig(model="test-model", max_turns=4),
    )
    result = await harness.run("What is 2+3?")
    assert result.final_text == "The sum is 5."
    assert result.turns == 2
    assert any(m.role == Role.TOOL and m.content == "5" for m in result.messages)


@pytest.mark.asyncio
async def test_openai_tools_family(tools: ToolRegistry) -> None:
    inference = ScriptedInference([ChatMessage(role=Role.ASSISTANT, content="hello")])
    harness = OpenAIToolsHarness(
        inference=inference,
        tools=tools,
        config=HarnessConfig(model="m"),
    )
    result = await harness.run("hi")
    assert result.final_text == "hello"


@pytest.mark.asyncio
async def test_react_harness_parses_action(tools: ToolRegistry) -> None:
    inference = ScriptedInference(
        [
            ChatMessage(
                role=Role.ASSISTANT,
                content=(
                    "Thought: I should add\n"
                    "Action: add\n"
                    'Action Input: {"a": 2, "b": 3}\n'
                ),
            ),
            ChatMessage(
                role=Role.ASSISTANT,
                content="Thought: done\nFinal Answer: 5",
            ),
        ]
    )
    harness = ReactHarness(
        inference=inference,
        tools=tools,
        config=HarnessConfig(model="m", max_turns=4),
    )
    result = await harness.run("2+3?")
    assert result.final_text == "5"
    assert any("Observation: 5" in (m.content or "") for m in result.messages)
