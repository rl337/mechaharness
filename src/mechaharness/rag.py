"""RAG retrieve seam — host-bound; no production backend in-tree yet.

Hosts (and story Configs) bind a :class:`RagRetriever` via
``MechaHarnessConfig.get_rag_retriever``. The ``context_pack`` Agentic Recipe
calls ``retrieve`` then :func:`~mechaharness.decision_plane_runtime.assemble_context_within_budget`.
Production adapters may judge relevance/trust/freshness inside ``retrieve``;
:class:`FixtureRagRetriever` returns a canned scored corpus for acceptance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict


class RagCandidate(BaseModel):
    """One retrieval hit, optionally pre-scored for packing."""

    model_config = ConfigDict(extra="allow")

    id: str
    text: str = ""
    tokens: int
    relevance: float | str | None = None
    trust: float | str | None = None
    freshness: float | str | None = None


class RagRetriever(ABC):
    """Host-owned retrieval. Library ships no production implementation."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 32,
    ) -> list[RagCandidate]:
        """Return candidates for ``query`` (scored or raw)."""


class UnboundRagRetriever(RagRetriever):
    """Default binding: fail loudly so hosts must configure a retriever."""

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 32,
    ) -> list[RagCandidate]:
        del query, limit
        raise RuntimeError(
            "RagRetriever is unbound; override MechaHarnessConfig.get_rag_retriever "
            "or register_instance(RagRetriever, …)"
        )


class FixtureRagRetriever(RagRetriever):
    """Deterministic corpus for stories / unit tests (retrieve + score stand-in)."""

    def __init__(
        self,
        candidates: Sequence[RagCandidate | Mapping[str, Any]] | None = None,
        *,
        query_filter: bool = False,
    ) -> None:
        self._candidates = [
            c if isinstance(c, RagCandidate) else RagCandidate.model_validate(c)
            for c in (candidates or [])
        ]
        self._query_filter = query_filter

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 32,
    ) -> list[RagCandidate]:
        rows = list(self._candidates)
        if self._query_filter and query.strip():
            q = query.lower()
            rows = [
                c
                for c in rows
                if q in c.text.lower() or q in c.id.lower()
            ]
        return rows[: max(0, limit)]


def candidates_as_pack_dicts(
    candidates: Sequence[RagCandidate],
) -> list[dict[str, Any]]:
    """Shape candidates for :func:`assemble_context_within_budget`."""
    out: list[dict[str, Any]] = []
    for c in candidates:
        row: dict[str, Any] = {
            "id": c.id,
            "tokens": c.tokens,
            "text": c.text,
            "relevance": c.relevance,
            "trust": c.trust,
            "freshness": c.freshness,
        }
        for key, value in c.model_dump(exclude_none=False).items():
            if key not in row:
                row[key] = value
        out.append(row)
    return out


__all__ = [
    "FixtureRagRetriever",
    "RagCandidate",
    "RagRetriever",
    "UnboundRagRetriever",
    "candidates_as_pack_dicts",
]
