"""Context / observation experiments (CTX-*) — off by default."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ObservationRef(BaseModel):
    """Immutable reference to original tool output (CTX-01)."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: f"obs:{uuid4()}")
    tool_name: str | None = None
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)


class ObservationStore:
    def __init__(self) -> None:
        self._items: dict[str, ObservationRef] = {}

    def put(self, ref: ObservationRef) -> ObservationRef:
        self._items[ref.id] = ref
        return ref

    def get(self, obs_id: str) -> ObservationRef | None:
        return self._items.get(obs_id)


class CtxFlags(BaseModel):
    """Independently toggleable CTX experiments (default all False)."""

    model_config = ConfigDict(extra="allow")

    observation_refs: bool = False
    evidence_reduction: bool = False
    economic_compaction: bool = False
    action_fusion: bool = False


class Receipt(BaseModel):
    model_config = ConfigDict(extra="allow")

    obs_id: str
    summary: str
    blockers: list[str] = Field(default_factory=list)
    fabricated: bool = False


def reduce_evidence(
    store: ObservationStore,
    obs_id: str,
    *,
    summary: str,
    blockers: Sequence[str] | None = None,
    flags: CtxFlags | None = None,
) -> Receipt:
    """Evidence-preserving reduction (CTX-02). Fabricated receipts fail lookup."""
    flags = flags or CtxFlags()
    if not flags.evidence_reduction:
        raise RuntimeError("CTX evidence_reduction is disabled")
    ref = store.get(obs_id)
    if ref is None:
        return Receipt(obs_id=obs_id, summary=summary, blockers=list(blockers or []), fabricated=True)
    return Receipt(
        obs_id=obs_id,
        summary=summary,
        blockers=list(blockers or []),
        fabricated=False,
    )


def compact_at_boundary(
    messages: Sequence[Mapping[str, Any]],
    *,
    flags: CtxFlags | None = None,
    keep_last: int = 4,
) -> list[dict[str, Any]]:
    """Economic compaction at semantic boundaries (CTX-03)."""
    flags = flags or CtxFlags()
    items = [dict(m) for m in messages]
    if not flags.economic_compaction or len(items) <= keep_last:
        return items
    head = items[0:1]
    tail = items[-keep_last:]
    return head + [{"role": "system", "content": "[compacted intermediate context]"}] + tail


def fuse_actions(
    steps: Sequence[str],
    *,
    allowed_sequences: Sequence[Sequence[str]],
    flags: CtxFlags | None = None,
) -> list[str] | None:
    """Permit predeclared fused sequences only (CTX-04)."""
    flags = flags or CtxFlags()
    if not flags.action_fusion:
        return None
    seq = list(steps)
    for allowed in allowed_sequences:
        if list(allowed) == seq:
            return seq
    return None
