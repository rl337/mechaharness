"""Observe / prepare / execute tool phases (MH-DOTS-03)."""

from __future__ import annotations

import pytest

from mechaharness.operation_registry import (
    OperationContract,
    OperationRegistry,
    assert_tool_phase_allows_effects,
)
from mechaharness.tools.base import Tool, ToolRegistry

_PHASE_EFFECTS = [
    ("observe", "none", True),
    ("observe", "read", True),
    ("observe", "write", False),
    ("observe", "external", False),
    ("observe", "unknown", False),
    ("prepare", "read", True),
    ("prepare", "write", False),
    ("prepare", "external", False),
    ("execute", "none", True),
    ("execute", "write", True),
    ("execute", "external", True),
    ("execute", "unknown", True),
]


@pytest.mark.parametrize(("phase", "effect", "allowed"), _PHASE_EFFECTS)
def test_assert_tool_phase_allows_effects(phase: str, effect: str, allowed: bool) -> None:
    if allowed:
        assert_tool_phase_allows_effects(phase, effect)
    else:
        with pytest.raises(ValueError, match="cannot declare"):
            assert_tool_phase_allows_effects(phase, effect)


def test_unknown_phase_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown tool_phase"):
        assert_tool_phase_allows_effects("act", "none")


@pytest.mark.parametrize(("phase", "effect", "allowed"), _PHASE_EFFECTS)
def test_registry_enforces_phase_on_register(phase: str, effect: str, allowed: bool) -> None:
    registry = OperationRegistry()
    contract = OperationContract(name="op", tool_phase=phase, external_effects=effect)  # type: ignore[arg-type]
    if allowed:
        registry.register("op", lambda **_: None, contract=contract)
        assert registry.contract("op").tool_phase == phase
    else:
        with pytest.raises(ValueError, match="cannot declare"):
            registry.register("op", lambda **_: None, contract=contract)
        assert not registry.supports("op")


def test_register_contract_enforces_phase() -> None:
    registry = OperationRegistry()
    with pytest.raises(ValueError):
        registry.register_contract(
            OperationContract(name="x", tool_phase="prepare", external_effects="write")
        )


def test_contract_defaults_to_execute() -> None:
    assert OperationContract(name="x").tool_phase == "execute"


def test_tool_stores_phase_and_defaults_to_execute() -> None:
    assert Tool("t", lambda: "x").tool_phase == "execute"
    assert Tool("t", lambda: "x", tool_phase="observe").tool_phase == "observe"
    tools = ToolRegistry()

    @tools.tool("peek", tool_phase="observe")
    def peek() -> str:
        return "ok"

    assert tools.get("peek").tool_phase == "observe"
