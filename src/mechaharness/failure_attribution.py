"""Structured failure attribution for traces (req 11).

In *How Anthropic runs large-scale code migrations with Claude Code*, the
Claude developer blog suggests fixing the process that produced a failure
rather than only patching one-off outputs
(https://claude.com/blog/ai-code-migration).
In *Continually improving our agent harness*, the Cursor developer blog
suggests retaining enough structure to attribute and re-evaluate harness
changes
(https://cursor.com/blog/continually-improving-agent-harness).
Structured categories let clients mine repeats across runs::

    >>> from mechaharness.failure_attribution import (
    ...     attribute_error, detect_repeated_failure_classes,
    ... )
    >>> attrs = [
    ...     attribute_error("no_runner:explore", node_id="b0"),
    ...     attribute_error("no_runner:explore", node_id="b1"),
    ...     attribute_error("permission_denied", node_id="write"),
    ... ]
    >>> attrs[0].category
    'linkage'
    >>> "no_runner" in detect_repeated_failure_classes(attrs)
    True

WalkingLabs P08 further asks that verification failures carry a responsible
node / repair target so routing can roll back to the layer that caused the
defect
(https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/)::

    >>> from mechaharness.failure_attribution import (
    ...     attribute_with_repair_target, select_rollback_target,
    ... )
    >>> from mechaharness.graph_transition import GraphTransition, TransitionContract
    >>> attr = attribute_with_repair_target(
    ...     "verification_failed", node_id="verify", repair_target="produce",
    ...     evidence_refs=["oracle:e2e"],
    ... )
    >>> attr.repair_target
    'produce'
    >>> contract = TransitionContract(transitions=[
    ...     GraphTransition(from_node="verify", kind="rollback", to_node="produce",
    ...                     reason="verification_failed"),
    ... ])
    >>> select_rollback_target(attr, contract)
    'produce'
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FailureCategory = Literal[
    "graph_topology",
    "routing",
    "context",
    "tools",
    "models",
    "evaluator_policy",
    "linkage",
    "environment",
    "unknown",
]


class FailureAttribution(BaseModel):
    """Enough structure to attribute failures across runs."""

    model_config = ConfigDict(extra="allow")

    category: FailureCategory = "unknown"
    node_id: str | None = None
    kind: str | None = None
    error: str | None = None
    repeated_class: str | None = None
    responsible_node: str | None = None
    repair_target: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    recommended_repair: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    def to_event_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def attribute_error(
    error: str | None,
    *,
    node_id: str | None = None,
    kind: str | None = None,
) -> FailureAttribution:
    """Map common error prefixes to attribution categories."""
    text = error or ""
    category: FailureCategory = "unknown"
    if text.startswith("no_runner:") or text.startswith("linkage_failed"):
        category = "linkage"
    elif text.startswith("missing_grant") or text == "permission_denied":
        category = "tools"
    elif text.startswith("incompatible_checkpoint"):
        category = "graph_topology"
    elif "environment" in text:
        category = "environment"
    elif text.startswith("subgraph_"):
        category = "graph_topology"
    elif text.startswith("verification"):
        category = "evaluator_policy"
    return FailureAttribution(
        category=category,
        node_id=node_id,
        kind=kind,
        error=error,
        repeated_class=text.split(":", 1)[0] if text else None,
        responsible_node=node_id,
    )


def attribute_with_repair_target(
    error: str | None,
    *,
    node_id: str | None = None,
    kind: str | None = None,
    responsible_node: str | None = None,
    repair_target: str | None = None,
    evidence_refs: list[str] | None = None,
    recommended_repair: str | None = None,
) -> FailureAttribution:
    """Attribute a failure and attach structured rollback / repair targets."""
    base = attribute_error(error, node_id=node_id, kind=kind)
    return base.model_copy(
        update={
            "responsible_node": responsible_node or node_id,
            "repair_target": repair_target,
            "evidence_refs": list(evidence_refs or ()),
            "recommended_repair": recommended_repair or repair_target,
        }
    )


def select_rollback_target(
    attribution: FailureAttribution,
    contract: Any,
) -> str | None:
    """Pick a rollback transition target matching repair_target / responsible_node."""
    target = attribution.repair_target or attribution.responsible_node
    transitions = list(getattr(contract, "transitions", None) or [])
    from_node = attribution.node_id
    rollbacks = [
        edge
        for edge in transitions
        if getattr(edge, "kind", None) == "rollback"
        and (not from_node or getattr(edge, "from_node", None) == from_node)
    ]
    for edge in rollbacks:
        if target is not None and getattr(edge, "to_node", None) == target:
            return str(edge.to_node)
    if rollbacks and getattr(rollbacks[0], "to_node", None):
        return str(rollbacks[0].to_node)
    return target


def detect_repeated_failure_classes(
    attributions: list[FailureAttribution],
    *,
    min_count: int = 2,
) -> list[str]:
    counts: dict[str, int] = {}
    for item in attributions:
        key = item.repeated_class or item.category
        counts[key] = counts.get(key, 0) + 1
    return sorted(k for k, n in counts.items() if n >= min_count)
