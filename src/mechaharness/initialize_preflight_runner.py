"""Graph node runners for the ``initialize_preflight`` Agentic Recipe."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome


class PreflightStampRunner(GraphNodeRunner):
    """Stamp a preflight phase as ok from fixture inputs (or default true)."""

    def __init__(
        self,
        *,
        kinds: Sequence[str],
        flag: str,
        input_key: str | None = None,
    ) -> None:
        self._kinds = list(kinds)
        self._flag = flag
        self._input_key = input_key or flag

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        payload = dict(node.payload)
        # Prefer explicit fixture on this node; else walk upstream produce-style bag.
        ok = payload.get(self._input_key)
        if ok is None:
            ok = True
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={**payload, self._flag: bool(ok), "ok": bool(ok)},
        )


class PreflightReadyRunner(GraphNodeRunner):
    """Emit readiness only when prior preflight stamps succeeded."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["preflight_ready"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        checks = (
            ("linkage", "linkage_ok"),
            ("capability_check", "capability_ok"),
            ("checkpoint_compat", "checkpoint_ok"),
        )
        results: dict[str, Any] = {}
        all_ok = True
        for nid, flag in checks:
            upstream = context.graph.nodes.get(nid)
            ok = bool(upstream.payload.get("ok", True)) if upstream else False
            results[flag] = ok
            all_ok = all_ok and ok
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                **results,
                "preflight_ok": all_ok,
                "ready": all_ok,
            },
        )


def initialize_preflight_runners() -> list[GraphNodeRunner]:
    return [
        PreflightStampRunner(kinds=["preflight_linkage"], flag="linkage_ok"),
        PreflightStampRunner(kinds=["preflight_capability"], flag="capability_ok"),
        PreflightStampRunner(kinds=["preflight_checkpoint"], flag="checkpoint_ok"),
        PreflightReadyRunner(),
    ]
