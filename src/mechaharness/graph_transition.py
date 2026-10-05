"""Declarative graph transitions distinct from dependency edges.

WalkingLabs lecture 14 and project P08 treat success/failure/retry/rollback/
escalation paths as first-class graph edges, separate from \"what must exist
first\" dependencies
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/,
https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/).

MechaHarness keeps ``DependencyEdge`` for prerequisites and adds
``TransitionContract`` for where execution goes next::

    >>> from mechaharness.graph_transition import (
    ...     GraphTransition, TransitionContract, TransitionKind, inspect_transitions,
    ... )
    >>> contract = TransitionContract(transitions=[
    ...     GraphTransition(from_node="produce", kind="success", to_node="verify"),
    ...     GraphTransition(from_node="verify", kind="rollback", to_node="produce",
    ...                     reason="verification_failed"),
    ...     GraphTransition(from_node="verify", kind="end", reason="accepted"),
    ... ])
    >>> kinds = {t.kind for t in inspect_transitions(contract, "verify")}
    >>> kinds == {"rollback", "end"}
    True
    >>> contract.validate_against_nodes({"produce", "verify"})
    []
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TransitionKind = Literal[
    "success",
    "predicate",
    "retry",
    "rollback",
    "escalate",
    "cancel",
    "end",
]


class GraphTransition(BaseModel):
    """One declared control-flow edge after a node completes or fails."""

    model_config = ConfigDict(extra="allow")

    from_node: str
    kind: TransitionKind
    to_node: str | None = None
    predicate: str | None = None
    reason: str = ""
    evidence_ref: str | None = None


class TransitionContract(BaseModel):
    """Collection of transitions for a graph; orthogonal to dependency edges."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    transitions: list[GraphTransition] = Field(default_factory=list)

    def for_node(self, node_id: str) -> list[GraphTransition]:
        return [t for t in self.transitions if t.from_node == node_id]

    def validate_against_nodes(self, node_ids: set[str]) -> list[str]:
        """Return human-readable issues (empty when valid)."""
        issues: list[str] = []
        for t in self.transitions:
            if t.from_node not in node_ids:
                issues.append(f"unknown from_node {t.from_node!r}")
            if t.kind != "end" and not t.to_node:
                issues.append(f"{t.kind} from {t.from_node!r} missing to_node")
            if t.to_node is not None and t.to_node not in node_ids:
                issues.append(f"unknown to_node {t.to_node!r}")
            if t.kind == "predicate" and not t.predicate:
                issues.append(f"predicate transition from {t.from_node!r} needs predicate")
            if t.kind == "rollback" and not t.reason:
                issues.append(f"rollback from {t.from_node!r} needs reason")
        return issues

    def choose(
        self,
        node_id: str,
        *,
        kind: TransitionKind,
        predicate_true: bool | None = None,
    ) -> GraphTransition | None:
        candidates = [t for t in self.for_node(node_id) if t.kind == kind]
        if kind == "predicate" and predicate_true is not None:
            # predicate_true selects the matching transition; false falls through.
            if not predicate_true:
                return None
        return candidates[0] if candidates else None


def inspect_transitions(
    contract: TransitionContract, node_id: str
) -> list[GraphTransition]:
    """List possible transitions from a node before execution."""
    return list(contract.for_node(node_id))


def transitions_payload(contract: TransitionContract) -> dict[str, Any]:
    return contract.model_dump(mode="json")
