"""Access grants, tool deny/allow, and tool cost on the shared harness loop."""

from __future__ import annotations

import pytest
from pyiv import get_injector

from mechaharness.core.access import (
    Ability,
    AccessPolicy,
    FsWrite,
    Grant,
    InMemoryAccessControl,
    grant_key,
)
from mechaharness.core.events import AccessCheck, Cost, InMemoryEventLog
from mechaharness.core.types import ChatMessage, Role, ToolCall
from mechaharness.di import MechaHarnessConfig
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness.react import ReactHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.tools.base import ToolRegistry
from tests.fakes import ScriptedInference


class WidgetGrant(Grant):
    namespace = "acme"
    name = "widget"


def write_tools() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(
        description="Write a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        grants=[FsWrite],
        ability=Ability.BASIC,
    )
    def write_file(path: str) -> str:
        return f"wrote {path}"

    return registry


def add_tools() -> ToolRegistry:
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


def test_grant_key_from_class_and_string() -> None:
    assert FsWrite.key() == "core:fs.write"
    assert grant_key(FsWrite) == "core:fs.write"
    assert grant_key("acme:unregistered") == "acme:unregistered"
    with pytest.raises(KeyError, match="unknown grant"):
        Grant.parse("acme:unregistered")


def test_bare_grant_is_rejected() -> None:
    with pytest.raises(ValueError, match="namespace:name"):
        grant_key("fs.write")


def test_access_policy_is_deny_by_default() -> None:
    policy = AccessPolicy()
    assert policy.allows([])
    assert not policy.allows([FsWrite])


def test_access_policy_requires_all_grants() -> None:
    policy = AccessPolicy(grants=[FsWrite, WidgetGrant])
    assert policy.allows([FsWrite])
    assert policy.allows(["acme:widget"])
    assert not policy.allows([FsWrite, "core:fs.read"])


def test_host_grant_subclass() -> None:
    assert WidgetGrant.key() == "acme:widget"
    assert Grant.parse("acme:widget") is WidgetGrant


def _walk_grants(base: type[Grant] = Grant) -> list[type[Grant]]:
    found: list[type[Grant]] = []
    stack = list(base.__subclasses__())
    while stack:
        cls = stack.pop()
        found.append(cls)
        stack.extend(cls.__subclasses__())
    return found


def test_grant_namespace_and_name_are_unique() -> None:
    concrete = [cls for cls in _walk_grants() if cls.namespace and cls.name]
    assert concrete, "expected concrete Grant subclasses"
    by_key: dict[str, str] = {}
    collisions: list[str] = []
    for cls in concrete:
        key = f"{cls.namespace}:{cls.name}"
        other = by_key.get(key)
        if other is not None:
            collisions.append(f"{key} used by {other} and {cls.__name__}")
        else:
            by_key[key] = cls.__name__
        assert cls.key() == key
    assert not collisions, "; ".join(collisions)


def _write_script() -> ScriptedInference:
    return ScriptedInference(
        [
            ChatMessage(
                role=Role.ASSISTANT,
                content=None,
                tool_calls=[ToolCall(id="1", name="write_file", arguments={"path": "a.txt"})],
            ),
            ChatMessage(role=Role.ASSISTANT, content="done"),
        ]
    )


@pytest.mark.asyncio
async def test_tool_denied_without_grant() -> None:
    log = InMemoryEventLog()
    harness = ToolLoopHarness(
        inference=_write_script(),
        tools=write_tools(),
        config=HarnessConfig(model="mock", max_turns=4),
        event_log=log,
        access=InMemoryAccessControl(event_log=log),
    )
    result = await harness.run("write a.txt")
    assert any("Permission denied" in (m.content or "") for m in result.messages)
    checks = log.query(types=[AccessCheck], run_id=result.events[0].run_id)
    assert checks[0].payload["allowed"] is False
    assert checks[0].payload["required"] == ["core:fs.write"]
    kinds = [entry.kind for entry in result.cost.entries]
    assert "tool" not in kinds
    assert any(event.type == "core:tool_result" for event in result.events)


@pytest.mark.asyncio
async def test_tool_runs_when_granted() -> None:
    log = InMemoryEventLog()
    harness = ToolLoopHarness(
        inference=_write_script(),
        tools=write_tools(),
        config=HarnessConfig(model="mock", max_turns=4),
        event_log=log,
        access=InMemoryAccessControl(event_log=log, grants=[FsWrite]),
    )
    result = await harness.run("write a.txt")
    assert result.final_text == "done"
    assert any(m.role == Role.TOOL and m.content == "wrote a.txt" for m in result.messages)
    checks = log.query(types=[AccessCheck], run_id=result.events[0].run_id)
    assert checks[0].payload["allowed"] is True
    tool_costs = [entry for entry in result.cost.entries if entry.kind == "tool"]
    assert len(tool_costs) == 1
    assert tool_costs[0].name == "write_file"
    assert tool_costs[0].units == Ability.BASIC.units
    types = [event.type for event in result.events]
    assert "core:tool_call" in types
    assert AccessCheck.key() in types
    assert Cost.key() in types


@pytest.mark.asyncio
async def test_ungranted_tool_still_runs_when_it_requires_nothing() -> None:
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
    log = InMemoryEventLog()
    harness = ToolLoopHarness(
        inference=inference,
        tools=add_tools(),
        config=HarnessConfig(model="mock", max_turns=4),
        event_log=log,
    )
    result = await harness.run("2+3?")
    assert result.final_text == "The sum is 5."
    assert result.cost.units == Ability.SIMPLE.units * 2 + Ability.SIMPLE.units
    kinds = [entry.kind for entry in result.cost.entries]
    assert kinds.count("inference") == 2
    assert kinds.count("tool") == 1
    checks = log.query(types=[AccessCheck], run_id=result.events[0].run_id)
    assert checks[0].payload["required"] == []
    assert checks[0].payload["allowed"] is True


@pytest.mark.asyncio
async def test_pass_through_does_not_emit_access_or_tool_cost() -> None:
    log = InMemoryEventLog()
    harness = PassThroughHarness(
        inference=ScriptedInference([ChatMessage(role=Role.ASSISTANT, content="ok")]),
        tools=write_tools(),
        config=HarnessConfig(model="mock"),
        event_log=log,
    )
    result = await harness.run("hi")
    types = [event.type for event in result.events]
    assert AccessCheck.key() not in types
    assert "core:tool_call" not in types
    assert result.cost.entries[0].kind == "inference"


@pytest.mark.asyncio
async def test_react_shared_loop_emits_access_and_cost() -> None:
    log = InMemoryEventLog()
    inference = ScriptedInference(
        [
            ChatMessage(
                role=Role.ASSISTANT,
                content=(
                    "Thought: write\n"
                    "Action: write_file\n"
                    'Action Input: {"path": "a.txt"}\n'
                ),
            ),
            ChatMessage(role=Role.ASSISTANT, content="Thought: done\nFinal Answer: wrote"),
        ]
    )
    harness = ReactHarness(
        inference=inference,
        tools=write_tools(),
        config=HarnessConfig(model="m", max_turns=4),
        event_log=log,
        access=InMemoryAccessControl(event_log=log, grants=[FsWrite]),
    )
    result = await harness.run("write")
    assert result.final_text == "wrote"
    assert any("Observation: wrote a.txt" in (m.content or "") for m in result.messages)
    types = [event.type for event in result.events]
    assert AccessCheck.key() in types
    assert "core:tool_call" in types
    assert "core:tool_result" in types
    assert Cost.key() in types
    assert result.cost.units >= Ability.SIMPLE.units + Ability.BASIC.units


class GrantConfig(MechaHarnessConfig):
    def __init__(
        self,
        inference: InferenceStrategy,
        tools: ToolRegistry,
        harness_config: HarnessConfig,
        grants: list[object],
    ) -> None:
        self._inference = inference
        self._tools = tools
        self._harness_config = harness_config
        self._grants = grants
        super().__init__()  # type: ignore[no-untyped-call]

    def get_inference_class(self) -> type[InferenceStrategy]:
        return type(self._inference)

    def get_harness_class(self) -> type[AbstractHarness]:
        return ToolLoopHarness

    def get_tools(self) -> ToolRegistry:
        return self._tools

    def get_harness_config(self) -> HarnessConfig:
        return self._harness_config

    def get_grants(self) -> list[object]:
        return self._grants

    def configure(self) -> None:
        super().configure()
        self.register_instance(InferenceStrategy, self._inference)


@pytest.mark.asyncio
async def test_di_get_grants_allows_tool() -> None:
    config = GrantConfig(
        _write_script(),
        write_tools(),
        HarnessConfig(model="mock", max_turns=4),
        grants=[FsWrite],
    )
    harness = get_injector(config).inject(AbstractHarness)
    result = await harness.run("write")
    assert result.final_text == "done"
    assert any(entry.kind == "tool" for entry in result.cost.entries)
