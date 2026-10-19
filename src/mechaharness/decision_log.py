"""Decision observability: EventLog subtype + decisions.jsonl (OBS-*).

Review audit (MH-PA-08 / MH-DOTS-09)
------------------------------------

An audit must reconstruct a review without model memory: which recipe ran,
what the policy decided and under which revision, how trusted the source was,
what scope was delegated, why something was denied, who approved it, and which
side effects actually happened. :class:`ReviewAuditRecord` composes the
optional audit fields on :class:`~mechaharness.decision_log.DecisionRecord` and
:class:`~mechaharness.trace_envelope.TraceEnvelope` into one flat record and
names whatever is still missing::

    >>> from mechaharness.decision_log import DecisionRecord, ReviewAuditRecord
    >>> decision = DecisionRecord(
    ...     eventId="e1", stateHash="h", policyVersion="p1", verdict="ALLOW",
    ...     recipeId="independent_review", recipeVersion="1",
    ...     approvalIds=["appr:1"], effectIds=["fx:1"],
    ... )
    >>> audit = ReviewAuditRecord.from_records(
    ...     decision, source_trust="trusted", delegated_scope="env:child-1",
    ...     policy_revision="rev-7",
    ... )
    >>> audit.missing_dimensions()
    []
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.events import CoreEvent, Event, EventLog, InMemoryEventLog, event_type_key
from mechaharness.inference.judge import Signal
from mechaharness.judgement_policy import JudgementFacts, JudgementPolicy, Verdict, decide
from mechaharness.trace_envelope import TraceEnvelope


class DecisionRecorded(CoreEvent):
    """Append-only decision / policy verdict event (``core:decision``)."""

    name = "decision"


class DecisionRecord(BaseModel):
    """OBS-02 schema for ``decisions.jsonl`` lines (learning-record fields)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = Field(default="1", alias="schemaVersion")
    event_id: str = Field(alias="eventId")
    run_id: str | None = Field(default=None, alias="runId")
    node_id: str | None = Field(default=None, alias="nodeId")
    attempt: int = 1
    state_hash: str = Field(alias="stateHash")
    state_snapshot_ref: str | None = Field(default=None, alias="stateSnapshotRef")
    question_set_version: str | None = Field(default=None, alias="questionSetVersion")
    model_revision: str | None = Field(default=None, alias="modelRevision")
    signals: dict[str, Any] = Field(default_factory=dict)
    policy_version: str = Field(alias="policyVersion")
    behavior_policy_version: str | None = Field(
        default=None, alias="behaviorPolicyVersion"
    )
    verdict: str
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    fallback: str | None = None
    latency_ms: float | None = Field(default=None, alias="latencyMs")
    action: str | None = None
    action_digest: str | None = Field(default=None, alias="actionDigest")
    allowed_candidates: list[str] = Field(
        default_factory=list, alias="allowedCandidates"
    )
    excluded_candidates: dict[str, str] = Field(
        default_factory=dict, alias="excludedCandidates"
    )
    proposed_action: str | None = Field(default=None, alias="proposedAction")
    executed_action: str | None = Field(default=None, alias="executedAction")
    context_manifest_ref: str | None = Field(
        default=None, alias="contextManifestRef"
    )
    resulting_state_ref: str | None = Field(
        default=None, alias="resultingStateRef"
    )
    verification_id: str | None = Field(default=None, alias="verificationId")
    outcome_id: str | None = Field(default=None, alias="outcomeId")
    termination_reason: str | None = Field(default=None, alias="terminationReason")
    action_selection_probability: float | None = Field(
        default=None, alias="actionSelectionProbability"
    )
    total_cost_usd: float | None = Field(default=None, alias="totalCostUsd")
    resource_conditions: dict[str, Any] = Field(
        default_factory=dict, alias="resourceConditions"
    )
    # Review-audit dimensions (MH-PA-08 / MH-DOTS-09); all optional.
    recipe_id: str | None = Field(default=None, alias="recipeId")
    recipe_version: str | None = Field(default=None, alias="recipeVersion")
    # Warehouse correlators (event-analytics-schema OBS-A01..A06); match graph events.
    graph_id: str | None = Field(default=None, alias="graphId")
    authorization_epoch: int | None = Field(default=None, alias="authorizationEpoch")
    parent_run_id: str | None = Field(default=None, alias="parentRunId")
    freshness_summary: dict[str, int] = Field(
        default_factory=dict, alias="freshnessSummary"
    )
    approval_ids: list[str] = Field(default_factory=list, alias="approvalIds")
    denial_ids: list[str] = Field(default_factory=list, alias="denialIds")
    effect_ids: list[str] = Field(default_factory=list, alias="effectIds")


def signals_to_map(signals: Sequence[Signal]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for signal in signals:
        out[signal.id] = signal.model_dump(by_alias=True, mode="json")
    return out


class DecisionLog:
    """Persist decisions to EventLog and optional JSONL (OBS-02)."""

    def __init__(
        self,
        event_log: EventLog | None = None,
        *,
        jsonl_path: Path | str | None = None,
        agent_id: str = "policy",
    ) -> None:
        self.event_log = event_log or InMemoryEventLog()
        self.jsonl_path = Path(jsonl_path) if jsonl_path else None
        self.agent_id = agent_id

    def record(self, record: DecisionRecord | Mapping[str, Any]) -> Event:
        rec = (
            record
            if isinstance(record, DecisionRecord)
            else DecisionRecord.model_validate(record)
        )
        payload = rec.model_dump(by_alias=True, mode="json")
        event = Event(
            type=event_type_key(DecisionRecorded),
            agent_id=self.agent_id,
            run_id=rec.run_id or str(uuid4()),
            payload=payload,
        )
        self.event_log.emit(event)
        if self.jsonl_path is not None:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, sort_keys=True) + "\n")
        return event

    def iter_jsonl(self) -> Iterable[DecisionRecord]:
        if self.jsonl_path is None or not self.jsonl_path.is_file():
            yield from ()
            return
        with self.jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield DecisionRecord.model_validate(json.loads(line))


def replay_verdict(
    *,
    facts: JudgementFacts | Mapping[str, Any],
    signals: Sequence[Signal] | Mapping[str, Signal],
    policy: JudgementPolicy | Mapping[str, Any],
) -> Verdict:
    """Deterministic judgement-policy replay without tool execution (OBS-03)."""
    return decide(facts, signals, policy)


class OfflineDecisionExport(BaseModel):
    """Versioned dataset export without future leakage (OBS-02)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = Field(default="1", alias="schemaVersion")
    split: str
    records: list[dict[str, Any]] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)
    redacted_fields: list[str] = Field(
        default_factory=lambda: ["credentials", "chain_of_thought"]
    )


def export_offline_dataset(
    records: Sequence[DecisionRecord],
    *,
    split: str,
    include_outcomes: bool = False,
) -> OfflineDecisionExport:
    """Export decision-time features; outcomes only when explicitly included."""
    rows: list[dict[str, Any]] = []
    lineage: list[str] = []
    for rec in records:
        row = rec.model_dump(by_alias=True, mode="json")
        lineage.append(rec.event_id)
        if not include_outcomes:
            row.pop("outcomeId", None)
            # Delayed outcomes must not leak into decision-time features
            row["outcomeId"] = None
        rows.append(row)
    return OfflineDecisionExport(split=split, records=rows, lineage=lineage)


class TopologySpan(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    start_ms: float
    end_ms: float
    parent: str | None = None


class TopologyMetrics(BaseModel):
    """OBS-04 execution-topology efficiency."""

    model_config = ConfigDict(extra="allow")

    graph_version: str
    critical_path_ms: float
    total_node_work_ms: float
    elapsed_ms: float
    observed_concurrency: float
    queue_wait_ms: float = 0.0
    notes: list[str] = Field(default_factory=list)


def compute_topology_metrics(
    spans: Sequence[TopologySpan],
    *,
    graph_version: str = "1",
    worker_count: int | None = None,
) -> TopologyMetrics:
    if not spans:
        return TopologyMetrics(
            graph_version=graph_version,
            critical_path_ms=0.0,
            total_node_work_ms=0.0,
            elapsed_ms=0.0,
            observed_concurrency=0.0,
        )
    total_work = sum(max(0.0, s.end_ms - s.start_ms) for s in spans)
    start = min(s.start_ms for s in spans)
    end = max(s.end_ms for s in spans)
    elapsed = max(0.0, end - start)
    # Critical path: longest chain by parent links if present, else elapsed
    by_name = {s.name: s for s in spans}
    def depth(span: TopologySpan) -> float:
        dur = max(0.0, span.end_ms - span.start_ms)
        if span.parent and span.parent in by_name:
            return dur + depth(by_name[span.parent])
        return dur

    critical = max(depth(s) for s in spans)
    concurrency = (total_work / elapsed) if elapsed > 0 else 0.0
    notes: list[str] = []
    if worker_count is not None:
        notes.append(f"worker_count={worker_count}")
        notes.append("parallel_efficiency_not_comparable_without_serial_baseline")
    return TopologyMetrics(
        graph_version=graph_version,
        critical_path_ms=critical,
        total_node_work_ms=total_work,
        elapsed_ms=elapsed,
        observed_concurrency=concurrency,
        notes=notes,
    )


class ReviewAuditRecord(BaseModel):
    """Everything an auditor needs to rebuild one review decision."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    decision_event_id: str
    run_id: str | None = None
    node_id: str | None = None
    verdict: str
    reason_codes: list[str] = Field(default_factory=list)
    policy_version: str | None = None
    policy_revision: str | None = None
    recipe_id: str | None = None
    recipe_version: str | None = None
    source_trust: str | None = None
    delegated_scope: str | None = None
    denial_reasons: list[str] = Field(default_factory=list)
    denial_ids: list[str] = Field(default_factory=list)
    approval_ids: list[str] = Field(default_factory=list)
    effect_ids: list[str] = Field(default_factory=list)
    executed_action: str | None = None
    freshness_summary: dict[str, int] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_records(
        cls,
        decision: DecisionRecord,
        envelope: TraceEnvelope | None = None,
        *,
        source_trust: str | None = None,
        delegated_scope: str | None = None,
        policy_revision: str | None = None,
        denial_reasons: Sequence[str] = (),
    ) -> ReviewAuditRecord:
        """Compose ``decision`` and optional ``envelope`` (decision wins on overlap)."""
        env = envelope or TraceEnvelope()
        return cls(
            decision_event_id=decision.event_id,
            run_id=decision.run_id,
            node_id=decision.node_id or env.node_id,
            verdict=decision.verdict,
            reason_codes=list(decision.reason_codes),
            policy_version=decision.policy_version,
            policy_revision=policy_revision or env.policy_revision,
            recipe_id=decision.recipe_id or env.recipe_id,
            recipe_version=decision.recipe_version or env.recipe_version,
            source_trust=source_trust,
            delegated_scope=delegated_scope or env.capability_envelope_ref,
            denial_reasons=list(denial_reasons),
            denial_ids=list(decision.denial_ids or env.denial_ids),
            approval_ids=list(decision.approval_ids or env.approval_ids),
            effect_ids=list(decision.effect_ids or env.effect_ids),
            executed_action=decision.executed_action,
            freshness_summary=dict(decision.freshness_summary or env.freshness_summary),
        )

    def missing_dimensions(self) -> list[str]:
        """Audit dimensions that cannot be reconstructed from this record."""
        required = {
            "recipe_id": self.recipe_id,
            "recipe_version": self.recipe_version,
            "policy_revision": self.policy_revision,
            "source_trust": self.source_trust,
            "delegated_scope": self.delegated_scope,
        }
        missing = [name for name, value in required.items() if not value]
        if self.verdict == "DENY":
            if not self.denial_reasons:
                missing.append("denial_reasons")
            if not self.denial_ids:
                missing.append("denial_ids")
        if self.verdict == "ASK_HUMAN" and not self.approval_ids:
            missing.append("approval_ids")
        if self.executed_action and not self.effect_ids:
            missing.append("effect_ids")
        return missing

    def reconstructable(self) -> bool:
        return not self.missing_dimensions()


class RecipeAuditRow(BaseModel):
    """Per-recipe rollup for quarterly audits (no transcripts needed)."""

    recipe_id: str
    recipe_version: str | None = None
    decisions: int = 0
    verdicts: dict[str, int] = Field(default_factory=dict)
    stale_evidence: int = 0
    fresh_evidence: int = 0


def summarize_recipe_audit(records: Sequence[DecisionRecord]) -> list[RecipeAuditRow]:
    """Group decisions by recipe selection and roll up verdicts and freshness."""
    rows: dict[tuple[str, str | None], RecipeAuditRow] = {}
    for record in records:
        if not record.recipe_id:
            continue
        key = (record.recipe_id, record.recipe_version)
        row = rows.setdefault(
            key, RecipeAuditRow(recipe_id=record.recipe_id, recipe_version=record.recipe_version)
        )
        row.decisions += 1
        row.verdicts[record.verdict] = row.verdicts.get(record.verdict, 0) + 1
        row.stale_evidence += record.freshness_summary.get("stale", 0)
        row.fresh_evidence += record.freshness_summary.get("fresh", 0)
    return [rows[k] for k in sorted(rows, key=lambda k: (k[0], k[1] or ""))]
