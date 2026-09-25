"""Context / observation experiments (CTX-*) — advanced flags off by default."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Literal
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
    """Independently toggleable CTX experiments (default advanced off)."""

    model_config = ConfigDict(extra="allow")

    observation_refs: bool = False
    evidence_reduction: bool = False
    economic_compaction: bool = False
    action_fusion: bool = False
    derived_memory: bool = False
    topology_provider: bool = False
    cache_aware_layout: bool = False


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
        return Receipt(
            obs_id=obs_id,
            summary=summary,
            blockers=list(blockers or []),
            fabricated=True,
        )
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


# --- CTX-05 context compiler -------------------------------------------------

class ContextManifest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    compiler_version: str = Field(default="1", alias="compilerVersion")
    selected: list[str] = Field(default_factory=list)
    omitted: list[str] = Field(default_factory=list)
    versions: dict[str, str] = Field(default_factory=dict)
    transformations: list[str] = Field(default_factory=list)
    token_estimate: int = Field(default=0, alias="tokenEstimate")
    unresolved_gaps: list[str] = Field(default_factory=list, alias="unresolvedGaps")
    blockers: list[str] = Field(default_factory=list)
    nondeterministic: bool = False


class CompiledContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    payload: dict[str, Any] = Field(default_factory=dict)
    manifest: ContextManifest
    deficit: bool = False


class ContextCompiler:
    """Versioned compilation boundary (CTX-05). Working context is ephemeral."""

    def __init__(self, *, version: str = "1", token_budget: int = 4096) -> None:
        self.version = version
        self.token_budget = token_budget

    def compile(
        self,
        *,
        state_revision: str,
        operation: str,
        sources: Mapping[str, str],
        mandatory: Sequence[str] | None = None,
        blockers: Sequence[str] | None = None,
        approvals: Sequence[str] | None = None,
        verification_obligations: Sequence[str] | None = None,
        needs_prompt: bool = True,
    ) -> CompiledContext:
        mandatory = list(mandatory or [])
        blockers = list(blockers or [])
        approvals = list(approvals or [])
        verification_obligations = list(verification_obligations or [])
        if not needs_prompt:
            return CompiledContext(
                payload={"operation": operation, "deterministic": True},
                manifest=ContextManifest(
                    compiler_version=self.version,
                    selected=[],
                    versions={"state": state_revision},
                    blockers=blockers,
                ),
            )

        selected: list[str] = []
        omitted: list[str] = []
        tokens = 0
        gaps: list[str] = []
        for key, text in sources.items():
            cost = max(1, len(text) // 4)
            if tokens + cost <= self.token_budget:
                selected.append(key)
                tokens += cost
            else:
                omitted.append(key)
                if key in mandatory:
                    gaps.append(key)

        for key in mandatory:
            if key not in sources:
                gaps.append(key)

        deficit = bool(gaps)
        payload: dict[str, Any] = {
            "operation": operation,
            "state_revision": state_revision,
            "content": {k: sources[k] for k in selected if k in sources},
            "blockers": blockers,
            "approvals": approvals,
            "verification_obligations": verification_obligations,
        }
        if deficit:
            payload["deficit"] = gaps
        return CompiledContext(
            payload=payload,
            manifest=ContextManifest(
                compiler_version=self.version,
                selected=selected,
                omitted=omitted,
                versions={"state": state_revision, "compiler": self.version},
                transformations=["budget_select"],
                token_estimate=tokens,
                unresolved_gaps=gaps,
                blockers=blockers,
            ),
            deficit=deficit,
        )


# --- CTX-06 / CTX-07 derived memory ------------------------------------------

MemoryOp = Literal["add", "supersede", "reinforce", "invalidate", "no_op"]
ValidationStatus = Literal["unvalidated", "valid", "invalid", "conflict"]


class DerivedMemoryRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid4()))
    role: Literal["episodic", "semantic", "procedural", "working"] = "semantic"
    content: str
    source_refs: list[str] = Field(default_factory=list)
    extractor_version: str = "1"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    recorded_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    scope: str = "default"
    validation_status: ValidationStatus = "unvalidated"
    retrieval_rank: float = 0.0
    authority: bool = False
    superseded_by: str | None = None
    tombstone: bool = False


class DerivedMemoryStore:
    """Event-backed derived views (CTX-06/07). Consolidation is optional."""

    def __init__(self) -> None:
        self._records: dict[str, DerivedMemoryRecord] = {}
        self._published: dict[str, DerivedMemoryRecord] = {}
        self._checkpoint_event: int = 0
        self._pending: list[DerivedMemoryRecord] = []

    def apply(self, op: MemoryOp, record: DerivedMemoryRecord) -> DerivedMemoryRecord:
        if op == "no_op":
            return record
        if op == "add":
            self._records[record.id] = record
            return record
        if op == "supersede":
            for old in self._records.values():
                if old.content == record.content and old.id != record.id:
                    old.superseded_by = record.id
            self._records[record.id] = record
            return record
        if op == "reinforce":
            existing = self._records.get(record.id)
            if existing is not None:
                existing.retrieval_rank += 1.0
                return existing
            self._records[record.id] = record
            return record
        if op == "invalidate":
            record.validation_status = "invalid"
            record.tombstone = True
            self._records[record.id] = record
            return record
        return record

    def consolidate_from(
        self, events: Sequence[Mapping[str, Any]], *, up_to: int
    ) -> None:
        """Idempotent consolidation against an event position (CTX-06)."""
        if up_to <= self._checkpoint_event:
            return
        for event in events[self._checkpoint_event : up_to]:
            content = str(event.get("content", ""))
            if not content:
                continue
            rec = DerivedMemoryRecord(
                content=content,
                source_refs=[str(event.get("id", ""))],
                recorded_at=str(event.get("time", "")),
            )
            self._pending.append(rec)
        # Atomic publish: swap only when complete
        published = dict(self._published)
        for rec in self._pending:
            published[rec.id] = rec
            self._records[rec.id] = rec
        self._published = published
        self._pending = []
        self._checkpoint_event = up_to

    def rebuild(self, events: Sequence[Mapping[str, Any]]) -> None:
        self._records.clear()
        self._published.clear()
        self._checkpoint_event = 0
        self._pending = []
        self.consolidate_from(events, up_to=len(events))

    def current(self, *, authoritative_only: bool = False) -> list[DerivedMemoryRecord]:
        items = [r for r in self._published.values() if not r.tombstone]
        if authoritative_only:
            items = [r for r in items if r.authority]
        return items

    def as_of(self, when: str) -> list[DerivedMemoryRecord]:
        out: list[DerivedMemoryRecord] = []
        for r in self._records.values():
            if r.tombstone:
                continue
            if r.valid_from and r.valid_from > when:
                continue
            if r.valid_to and r.valid_to <= when:
                continue
            out.append(r)
        return out

    def retrieval_candidates(self) -> list[DerivedMemoryRecord]:
        """Rank must not confer authority (CTX-07)."""
        return sorted(
            (r for r in self._published.values() if not r.tombstone),
            key=lambda r: r.retrieval_rank,
            reverse=True,
        )


# --- CTX-08 topology provider ------------------------------------------------

class TopologyEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str
    symbols: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    content_hash: str
    unsupported: bool = False


class TopologyView(BaseModel):
    model_config = ConfigDict(extra="allow")

    revision: str
    parser_version: str = "deterministic-1"
    entries: list[TopologyEntry] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)


class RepositoryTopologyProvider:
    """Budgeted repo map; stale maps fall back to source inspection (CTX-08)."""

    def __init__(self) -> None:
        self._by_revision: dict[str, TopologyView] = {}
        self._sources: dict[str, str] = {}

    def index(
        self,
        *,
        revision: str,
        files: Mapping[str, str],
        budget: int = 32,
    ) -> TopologyView:
        entries: list[TopologyEntry] = []
        omissions: list[str] = []
        for i, (path, content) in enumerate(files.items()):
            self._sources[f"{revision}:{path}"] = content
            if i >= budget:
                omissions.append(path)
                continue
            symbols = [
                line.strip()
                for line in content.splitlines()
                if line.startswith("def ")
            ]
            entries.append(
                TopologyEntry(
                    path=path,
                    symbols=symbols,
                    content_hash=str(hash(content)),
                    unsupported="\0" in content,
                )
            )
        view = TopologyView(revision=revision, entries=entries, omissions=omissions)
        self._by_revision[revision] = view
        return view

    def get(self, revision: str) -> TopologyView | None:
        return self._by_revision.get(revision)

    def source(self, revision: str, path: str) -> str | None:
        return self._sources.get(f"{revision}:{path}")

    def invalidate_path(self, revision: str, path: str) -> None:
        view = self._by_revision.get(revision)
        if view is None:
            return
        view.entries = [e for e in view.entries if e.path != path]
        view.omissions = [p for p in view.omissions if p != path]


# --- CTX-09 cache-aware layout -----------------------------------------------

class CacheLayout(BaseModel):
    model_config = ConfigDict(extra="allow")

    prefix_identity: str
    stable_prefix: list[str] = Field(default_factory=list)
    semi_stable: list[str] = Field(default_factory=list)
    dynamic_tail: list[str] = Field(default_factory=list)
    provider: str = "unknown"
    diagnostics: dict[str, Any] = Field(default_factory=dict)


def compile_cache_aware_layout(
    *,
    policy_blocks: Sequence[str],
    relevant: Sequence[str],
    dynamic: Sequence[str],
    flags: CtxFlags | None = None,
    policy_version: str = "1",
) -> CacheLayout:
    flags = flags or CtxFlags()
    if not flags.cache_aware_layout:
        return CacheLayout(
            prefix_identity=f"policy:{policy_version}",
            dynamic_tail=list(policy_blocks) + list(relevant) + list(dynamic),
            diagnostics={"enabled": False},
        )
    return CacheLayout(
        prefix_identity=f"policy:{policy_version}",
        stable_prefix=list(policy_blocks),
        semi_stable=list(relevant),
        dynamic_tail=list(dynamic),
        diagnostics={"enabled": True},
    )
