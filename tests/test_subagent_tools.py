"""Opt-in subagent EventLog query tools."""

from __future__ import annotations

import json

import pytest

from mechaharness.core.events import InMemoryEventLog
from mechaharness.core.types import ChatMessage, Role
from mechaharness.harness.base import HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.tools.base import ToolRegistry
from tests.fakes import ScriptedInference
from tests.support.di import make_harness


@pytest.mark.asyncio
async def test_subagent_tools_list_and_query() -> None:
    log = InMemoryEventLog()
    child = make_harness(
        ScriptedInference([ChatMessage(role=Role.ASSISTANT, content="inner")]),
        config=HarnessConfig(model="child"),
        harness_cls=PassThroughHarness,
        event_log=log,
        agent_id="child-1",
    )
    parent = make_harness(
        child,
        config=HarnessConfig(model="parent", subagent_tools=True),
        harness_cls=PassThroughHarness,
        event_log=log,
        agent_id="parent-1",
        include_subagent_tools=True,
    )
    await parent.run("go")
    assert "list_subagents" in parent.tools
    assert "get_subagent_events" in parent.tools
    body = json.loads((await parent.tools.execute("list_subagents", {}, "t1")).content)
    assert body[0]["agent_id"] == "child-1"
    events = json.loads(
        (
            await parent.tools.execute(
                "get_subagent_events",
                {"agent_id": "child-1"},
                "t2",
            )
        ).content
    )
    assert events["count"] >= 1
    assert events["events"][0]["agent_id"] == "child-1"


@pytest.mark.asyncio
async def test_subagent_tools_not_installed_by_default() -> None:
    harness = make_harness(
        ScriptedInference([ChatMessage(role=Role.ASSISTANT, content="x")]),
        tools=ToolRegistry(),
        config=HarnessConfig(model="m"),
        harness_cls=ToolLoopHarness,
    )
    assert "list_subagents" not in harness.tools
