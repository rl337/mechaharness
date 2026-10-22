"""Graph node runners for the ``independent_review`` Agentic Recipe."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


class IndependentProduceRunner(GraphNodeRunner):
    """Stamp a fixture artifact for independent review (no producer reasoning)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["produce"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        payload = dict(node.payload)
        artifact = _mapping(payload.get("artifact"))
        if not artifact:
            artifact = {
                "text": str(payload.get("text") or "draft"),
                "id": str(payload.get("artifact_id") or "artifact-1"),
            }
        # Producer reasoning stays on the produce node only — reviewers omit it.
        reasoning = payload.get("producer_reasoning")
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **payload,
                "artifact": artifact,
                "producer_reasoning": reasoning,
            },
        )


class IndependentReviewRunner(GraphNodeRunner):
    """Isolated reviewer: artifact + acceptance only; fixture findings."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["review"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        produce = context.graph.nodes.get("produce")
        produce_payload = dict(produce.payload) if produce is not None else {}
        artifact = _mapping(produce_payload.get("artifact"))
        omit = bool(node.payload.get("omit_producer_reasoning", True))
        findings_table = list(produce_payload.get("review_findings") or [])
        index = 0
        if node.id.startswith("review_"):
            try:
                index = int(node.id.rsplit("_", 1)[-1])
            except ValueError:
                index = 0
        finding: Any = None
        if index < len(findings_table):
            finding = findings_table[index]
        elif node.payload.get("finding") is not None:
            finding = node.payload.get("finding")
        else:
            finding = {"id": f"finding-{index}", "severity": "note"}
        # Isolation: never copy producer_reasoning onto the review payload.
        out = {
            **dict(node.payload),
            "artifact": artifact,
            "finding": finding,
            "saw_producer_reasoning": False if omit else (
                produce_payload.get("producer_reasoning") is not None
            ),
            "omit_producer_reasoning": omit,
        }
        if not omit and produce_payload.get("producer_reasoning") is not None:
            out["producer_reasoning"] = produce_payload.get("producer_reasoning")
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload=out)


class AggregateReviewsRunner(GraphNodeRunner):
    """Union findings and retain disagreement across reviewers."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["aggregate_reviews"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        findings: list[Any] = []
        omit_flags: list[bool] = []
        for nid, review_node in sorted(context.graph.nodes.items()):
            if not nid.startswith("review_"):
                continue
            payload = dict(review_node.payload)
            findings.append(payload.get("finding"))
            omit_flags.append(bool(payload.get("omit_producer_reasoning", True)))
        # Disagreement = more than one distinct finding payload.
        serialized = [repr(f) for f in findings]
        retain = bool(node.payload.get("retain_disagreement", True))
        disagreement = len(set(serialized)) > 1
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "findings": findings,
                "finding_count": len(findings),
                "review_count": len(findings),
                "retain_disagreement": retain,
                "disagreement_retained": retain and disagreement,
                "omit_producer_reasoning": all(omit_flags) if omit_flags else True,
            },
        )


def independent_review_runners() -> list[GraphNodeRunner]:
    return [
        IndependentProduceRunner(),
        IndependentReviewRunner(),
        AggregateReviewsRunner(),
    ]
