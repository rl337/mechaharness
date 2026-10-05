"""Unit coverage for graph transition contracts."""

from __future__ import annotations

from mechaharness.graph_transition import (
    GraphTransition,
    TransitionContract,
    inspect_transitions,
)


def test_validate_and_inspect() -> None:
    contract = TransitionContract(
        transitions=[
            GraphTransition(from_node="a", kind="success", to_node="b"),
            GraphTransition(from_node="b", kind="rollback", to_node="a", reason="bad"),
            GraphTransition(from_node="b", kind="end", reason="ok"),
        ]
    )
    assert contract.validate_against_nodes({"a", "b"}) == []
    assert {t.kind for t in inspect_transitions(contract, "b")} == {"rollback", "end"}
    assert contract.choose("a", kind="success") is not None
    assert contract.choose("b", kind="escalate") is None


def test_unknown_nodes_reported() -> None:
    contract = TransitionContract(
        transitions=[GraphTransition(from_node="missing", kind="end")]
    )
    issues = contract.validate_against_nodes({"a"})
    assert any("from_node" in i for i in issues)
