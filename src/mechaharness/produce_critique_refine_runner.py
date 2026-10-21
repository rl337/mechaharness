"""Graph node runners for the ``produce_critique_refine`` Agentic Recipe."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _stop_max_iterations(node: GraphNode) -> int:
    stop = node.stop_contract
    if isinstance(stop, Mapping):
        if stop.get("max_iterations") is not None:
            return int(stop["max_iterations"])
        return 2
    value = getattr(stop, "max_iterations", None) if stop is not None else None
    if value is not None:
        return int(value)
    return 2


class PcrProduceRunner(GraphNodeRunner):
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
            artifact = {"text": str(payload.get("text") or "draft"), "ok": False}
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **payload,
                "artifact": artifact,
                "producer_reasoning": payload.get("producer_reasoning"),
            },
        )


class CritiqueRunner(GraphNodeRunner):
    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["critique"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        produce = context.graph.nodes.get("produce")
        produce_payload = dict(produce.payload) if produce else {}
        artifact = _mapping(produce_payload.get("artifact"))
        defects = list(
            produce_payload.get("critique_findings")
            or node.payload.get("critique_findings")
            or ["defect"]
        )
        omit = bool(node.payload.get("omit_producer_reasoning", True))
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "artifact": artifact,
                "defects": defects,
                "defect_count": len(defects),
                "omit_producer_reasoning": omit,
                "saw_producer_reasoning": False if omit else (
                    produce_payload.get("producer_reasoning") is not None
                ),
                "isolated_context": True,
            },
        )


class RefineRunner(GraphNodeRunner):
    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["refine"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        critique = context.graph.nodes.get("critique")
        produce = context.graph.nodes.get("produce")
        defects = list((critique.payload.get("defects") if critique else None) or [])
        max_rounds = _stop_max_iterations(node)
        rounds = 0
        remaining = list(defects)
        while remaining and rounds < max_rounds:
            rounds += 1
            remaining = remaining[1:]  # clear one defect per round
        artifact = _mapping(produce.payload.get("artifact") if produce else None)
        if not remaining:
            artifact = {**artifact, "ok": True}
            if produce is not None:
                produce.payload = {**dict(produce.payload), "artifact": artifact}
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "rounds_used": rounds,
                "remaining_defects": remaining,
                "findings_cleared": not remaining,
                "artifact": artifact,
            },
        )


class PcrCompleteRunner(GraphNodeRunner):
    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["complete"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        refine = context.graph.nodes.get("refine")
        refine_payload = dict(refine.payload) if refine else {}
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "rounds_used": int(refine_payload.get("rounds_used") or 0),
                "findings_cleared": bool(refine_payload.get("findings_cleared")),
                "final_status": (
                    "succeeded"
                    if refine_payload.get("findings_cleared")
                    else "failed"
                ),
            },
        )


def produce_critique_refine_runners() -> list[GraphNodeRunner]:
    return [
        PcrProduceRunner(),
        CritiqueRunner(),
        RefineRunner(),
        PcrCompleteRunner(),
    ]
