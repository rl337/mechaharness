"""Observe / prepare / execute tool phases (MH-DOTS-03)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mechaharness.operation_registry import (
    OperationContract,
    OperationRegistry,
    assert_tool_phase_allows_effects,
)
from mechaharness.tools.base import Tool, ToolRegistry


@dataclass(frozen=True)
class _PhaseEffectCase:
    phase: str
    effect: str
    allowed: bool


_PHASE_EFFECTS = [
    _PhaseEffectCase("observe", "none", True),
    _PhaseEffectCase("observe", "read", True),
    _PhaseEffectCase("observe", "write", False),
    _PhaseEffectCase("observe", "external", False),
    _PhaseEffectCase("observe", "unknown", False),
    _PhaseEffectCase("prepare", "read", True),
    _PhaseEffectCase("prepare", "write", False),
    _PhaseEffectCase("prepare", "external", False),
    _PhaseEffectCase("execute", "none", True),
    _PhaseEffectCase("execute", "write", True),
    _PhaseEffectCase("execute", "external", True),
    _PhaseEffectCase("execute", "unknown", True),
]


@pytest.mark.parametrize(
    "case", _PHASE_EFFECTS, ids=lambda c: f"{c.phase}_{c.effect}"
)
def test_phase_effect_matrix(case: _PhaseEffectCase) -> None:
    """Both the free function and OperationRegistry share the same matrix."""
    if case.allowed:
        assert_tool_phase_allows_effects(case.phase, case.effect)
    else:
        with pytest.raises(ValueError, match="cannot declare"):
            assert_tool_phase_allows_effects(case.phase, case.effect)

    registry = OperationRegistry()
    contract = OperationContract(
        name="op", tool_phase=case.phase, external_effects=case.effect  # type: ignore[arg-type]
    )
    if case.allowed:
        registry.register("op", lambda **_: None, contract=contract)
        assert registry.contract("op").tool_phase == case.phase
    else:
        with pytest.raises(ValueError, match="cannot declare"):
            registry.register("op", lambda **_: None, contract=contract)
        assert not registry.supports("op")


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda: assert_tool_phase_allows_effects("act", "none"), "unknown tool_phase"),
        (
            lambda: OperationRegistry().register_contract(
                OperationContract(name="x", tool_phase="prepare", external_effects="write")
            ),
            "cannot declare",
        ),
    ],
    ids=["unknown_phase", "register_contract_prepare_write"],
)
def test_phase_rejects(call, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        call()


def test_contract_and_tool_default_to_execute() -> None:
    assert OperationContract(name="x").tool_phase == "execute"
    assert Tool("t", lambda: "x").tool_phase == "execute"
    assert Tool("t", lambda: "x", tool_phase="observe").tool_phase == "observe"
    tools = ToolRegistry()

    @tools.tool("peek", tool_phase="observe")
    def peek() -> str:
        return "ok"

    assert tools.get("peek").tool_phase == "observe"
