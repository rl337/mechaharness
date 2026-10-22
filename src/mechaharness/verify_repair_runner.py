"""Graph node runners for the ``verify_repair`` Agentic Recipe."""

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
        return int(node.payload.get("max_iterations") or 3)
    value = getattr(stop, "max_iterations", None) if stop is not None else None
    if value is not None:
        return int(value)
    return int(node.payload.get("max_iterations") or 3)


class ProduceRunner(GraphNodeRunner):
    """Stamp a fixture artifact onto the produce node."""

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
                "ok": bool(payload.get("initial_verify_ok", False)),
            }
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={**payload, "artifact": artifact},
        )


class VerifyRunner(GraphNodeRunner):
    """Verify the upstream produce artifact (fixture oracle)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["verify"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        produce = context.graph.nodes.get("produce")
        artifact = _mapping(produce.payload.get("artifact") if produce else None)
        passed = bool(artifact.get("ok"))
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "verification_passed": passed,
                "artifact": artifact,
            },
        )


class RepairRunner(GraphNodeRunner):
    """Bounded repair loop embedded in one node (executor has no StopContract walk)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["repair"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        verify = context.graph.nodes.get("verify")
        produce = context.graph.nodes.get("produce")
        verified = bool(verify.payload.get("verification_passed")) if verify else False
        artifact = _mapping(
            (produce.payload.get("artifact") if produce else None)
            or (verify.payload.get("artifact") if verify else None)
        )
        max_iters = _stop_max_iterations(node)
        repairs_needed = int(
            (produce.payload.get("repairs_needed") if produce else None)
            or node.payload.get("repairs_needed")
            or 0
        )
        attempts = 0
        if not verified:
            if repairs_needed <= 0:
                attempts = min(1, max_iters)
                artifact = {**artifact, "ok": False}
            else:
                while attempts < max_iters:
                    attempts += 1
                    if attempts >= repairs_needed:
                        artifact = {**artifact, "ok": True}
                        verified = True
                        break
        if produce is not None:
            produce.payload = {**dict(produce.payload), "artifact": artifact}
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "repair_attempts": attempts,
                "verification_passed": verified,
                "artifact": artifact,
            },
        )


class CompleteRunner(GraphNodeRunner):
    """Terminal complete — records final status from repair/verify."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["complete"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        repair = context.graph.nodes.get("repair")
        verify = context.graph.nodes.get("verify")
        passed = False
        attempts = 0
        if repair is not None:
            passed = bool(repair.payload.get("verification_passed"))
            attempts = int(repair.payload.get("repair_attempts") or 0)
        elif verify is not None:
            passed = bool(verify.payload.get("verification_passed"))
        final_status = "succeeded" if passed else "failed"
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "verification_passed": passed,
                "repair_attempts": attempts,
                "final_status": final_status,
            },
        )


def verify_repair_runners() -> list[GraphNodeRunner]:
    return [
        ProduceRunner(),
        VerifyRunner(),
        RepairRunner(),
        CompleteRunner(),
    ]
