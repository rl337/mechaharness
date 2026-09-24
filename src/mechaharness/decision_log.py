"""Decision observability: EventLog subtype + decisions.jsonl (OBS-*)."""

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


class DecisionRecorded(CoreEvent):
    """Append-only decision / policy verdict event (``core:decision``)."""

    name = "decision"


class DecisionRecord(BaseModel):
    """OBS-02 schema for ``decisions.jsonl`` lines."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = Field(default="1", alias="schemaVersion")
    event_id: str = Field(alias="eventId")
    run_id: str | None = Field(default=None, alias="runId")
    node_id: str | None = Field(default=None, alias="nodeId")
    attempt: int = 1
    state_hash: str = Field(alias="stateHash")
    question_set_version: str | None = Field(default=None, alias="questionSetVersion")
    model_revision: str | None = Field(default=None, alias="modelRevision")
    signals: dict[str, Any] = Field(default_factory=dict)
    policy_version: str = Field(alias="policyVersion")
    verdict: str
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    fallback: str | None = None
    latency_ms: float | None = Field(default=None, alias="latencyMs")
    action: str | None = None
    action_digest: str | None = Field(default=None, alias="actionDigest")


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
            return []
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
