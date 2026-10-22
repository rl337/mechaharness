"""Graph node runners for the ``environment_repair`` Agentic Recipe."""

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


class EnvDiagnoseRunner(GraphNodeRunner):
    """List missing environment capabilities from fixture inputs."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["env_diagnose"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        payload = dict(node.payload)
        missing = list(payload.get("missing_capabilities") or [])
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **payload,
                "missing_capabilities": missing,
                "needs_repair": bool(missing),
            },
        )


class EnvRepairRunner(GraphNodeRunner):
    """Bounded env repair: clear missing capabilities under stop contract."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["env_repair"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        diagnose = context.graph.nodes.get("diagnose")
        diagnose_payload = dict(diagnose.payload) if diagnose else {}
        missing = list(diagnose_payload.get("missing_capabilities") or [])
        max_iters = _stop_max_iterations(node)
        repairs_needed = int(
            diagnose_payload.get("repairs_needed")
            or node.payload.get("repairs_needed")
            or (1 if missing else 0)
        )
        attempts = 0
        remaining = list(missing)
        if remaining:
            while attempts < max_iters and attempts < max(repairs_needed, 1):
                attempts += 1
                if attempts >= repairs_needed:
                    remaining = []
                    break
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "repair_attempts": attempts,
                "missing_capabilities": remaining,
                "repaired": not remaining,
            },
        )


class EnvRecheckRunner(GraphNodeRunner):
    """Post-repair environment recheck."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["env_recheck"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        repair = context.graph.nodes.get("repair_env")
        repair_payload = dict(repair.payload) if repair else {}
        ok = bool(repair_payload.get("repaired", True)) and not list(
            repair_payload.get("missing_capabilities") or []
        )
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "environment_ok": ok,
                "recheck_ok": ok,
                "repair_attempts": int(repair_payload.get("repair_attempts") or 0),
            },
        )


def environment_repair_runners() -> list[GraphNodeRunner]:
    return [EnvDiagnoseRunner(), EnvRepairRunner(), EnvRecheckRunner()]
