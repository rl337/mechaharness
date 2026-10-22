"""Graph node runners for the ``context_pack`` Agentic Recipe."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mechaharness.decision_plane_runtime import assemble_context_within_budget
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.rag import RagCandidate, RagRetriever, candidates_as_pack_dicts


class RagRetrieveRunner(GraphNodeRunner):
    """Call host-bound :class:`RagRetriever` and stash candidates on the node."""

    def __init__(
        self,
        retriever: RagRetriever,
        *,
        kinds: Sequence[str] | None = None,
    ) -> None:
        self._retriever = retriever
        self._kinds = list(kinds or ["rag_retrieve"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        query = str(node.payload.get("query") or "")
        limit = int(node.payload.get("limit") or 32)
        try:
            hits = await self._retriever.retrieve(query, limit=limit)
        except Exception as exc:  # noqa: BLE001
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error=str(exc),
                payload=dict(node.payload),
            )
        candidates = [
            h if isinstance(h, RagCandidate) else RagCandidate.model_validate(h)
            for h in hits
        ]
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "candidates": [c.model_dump() for c in candidates],
                "candidate_count": len(candidates),
            },
        )


class RagPackRunner(GraphNodeRunner):
    """Pack upstream retrieve candidates with ``assemble_context_within_budget``."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["rag_pack"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        upstream = context.graph.nodes.get("retrieve")
        raw_candidates: list[dict[str, Any]] = []
        if upstream is not None:
            raw_candidates = list(upstream.payload.get("candidates") or [])
        if not raw_candidates and node.payload.get("candidates"):
            raw_candidates = list(node.payload.get("candidates") or [])
        candidates = [
            c if isinstance(c, RagCandidate) else RagCandidate.model_validate(c)
            for c in raw_candidates
        ]
        pack_rows = candidates_as_pack_dicts(candidates)
        token_budget = int(node.payload.get("token_budget") or 256)
        selected = assemble_context_within_budget(
            pack_rows,
            token_budget=token_budget,
            min_relevance=float(node.payload.get("min_relevance") or 0.0),
            min_trust=float(node.payload.get("min_trust") or 0.0),
            min_freshness=float(node.payload.get("min_freshness") or 0.0),
        )
        by_id = {str(r["id"]): r for r in pack_rows}
        total = sum(int(by_id[cid]["tokens"]) for cid in selected if cid in by_id)
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "selected_ids": selected,
                "token_total": total,
                "within_budget": total <= token_budget,
                "candidate_count": len(candidates),
            },
        )


__all__ = [
    "RagPackRunner",
    "RagRetrieveRunner",
]
