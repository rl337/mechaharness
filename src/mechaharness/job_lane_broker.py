"""Job lanes and JobLaneBroker: lane-scoped run sequences and authorized observe.

See ``docs/requirements/job-lane-broker.md`` (JL-01..10). Replaces the interim
cross-task isolation framing for product stories; the deprecated
:class:`~mechaharness.isolation.cross_task_isolation.CrossTaskIsolationGuard`
remains as a thin compatibility surface.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.core.exceptions import MechaHarnessError
from mechaharness.handoff_record import HandoffRecord
from mechaharness.iso_timestamp import parse_iso_timestamp
from mechaharness.walk_bag import FileArtifact, WalkBag

ExposureMode = Literal["open", "deny_all", "allow_lanes"]
ObserveStatus = Literal["ok", "denied"]


class IsolationViolation(MechaHarnessError):
    """A lane observe or publish violated exposure / ownership rules.

    Kept as the shared deny exception name so the deprecated cross-task shim
    and the broker raise the same type.
    """


class ExposureRule(BaseModel):
    """Publisher policy for meta or one bag key."""

    model_config = ConfigDict(extra="forbid")

    mode: ExposureMode = "deny_all"
    lanes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _allow_lanes_need_names(self) -> ExposureRule:
        if self.mode == "allow_lanes" and not self.lanes:
            raise ValueError("allow_lanes exposure requires a non-empty lanes list")
        if self.mode != "allow_lanes" and self.lanes:
            raise ValueError("lanes is only valid when mode is allow_lanes")
        return self


class JobLane(BaseModel):
    """Named pipeline identity with per-meta / per-key exposure (JL-01)."""

    model_config = ConfigDict(extra="forbid")

    lane_id: str
    meta: ExposureRule = Field(default_factory=ExposureRule)
    keys: dict[str, ExposureRule] = Field(default_factory=dict)


class LaneGrant(BaseModel):
    """Standing permission for a caller lane to observe a publisher lane."""

    model_config = ConfigDict(extra="forbid")

    from_lane: str
    to_lane: str
    keys: list[str] = Field(default_factory=list)
    meta: bool = False


class ObserveSelector(BaseModel):
    """Pick one run from a lane sequence (JL-04)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    latest: bool = False
    before: str | None = None
    at_or_before: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> ObserveSelector:
        flags = [
            self.run_id is not None,
            self.latest,
            self.before is not None,
            self.at_or_before is not None,
        ]
        if sum(1 for f in flags if f) != 1:
            raise ValueError(
                "selector needs exactly one of run_id, latest, before, at_or_before"
            )
        return self


class ObserveResult(BaseModel):
    """Typed observe outcome (JL-05); deny is not silent."""

    model_config = ConfigDict(extra="forbid")

    status: ObserveStatus
    reason: str | None = None
    run_id: str | None = None
    value: Any = None
    meta: dict[str, Any] | None = None


@dataclass
class _LaneRun:
    run_id: str
    started_at: datetime
    bag: WalkBag = field(default_factory=WalkBag)
    meta: dict[str, Any] = field(default_factory=dict)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, FileArtifact):
        return value.model_dump(exclude_none=True)
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    return value


def _exposure_allows(rule: ExposureRule, caller_lane: str) -> bool:
    if rule.mode == "open":
        return True
    if rule.mode == "deny_all":
        return False
    return caller_lane in rule.lanes


class JobLaneBroker:
    """Owns per-lane run sequences, bags, exposure, grants, and observe (JL-02..08)."""

    def __init__(self, lanes: Mapping[str, JobLane] | None = None) -> None:
        self._lanes: dict[str, JobLane] = {lid: lane for lid, lane in (lanes or {}).items()}
        self._runs: dict[str, list[_LaneRun]] = {lid: [] for lid in self._lanes}
        self._grants: list[LaneGrant] = []
        self._handoff_keys: dict[tuple[str, str], set[str]] = {}
        self._handoff_meta: set[tuple[str, str]] = set()

    def register_lane(self, lane: JobLane) -> None:
        if lane.lane_id in self._lanes:
            raise IsolationViolation(f"lane {lane.lane_id!r} already registered")
        self._lanes[lane.lane_id] = lane
        self._runs[lane.lane_id] = []

    def lanes(self) -> dict[str, JobLane]:
        return dict(self._lanes)

    def grant(
        self,
        *,
        from_lane: str,
        to_lane: str,
        keys: list[str] | None = None,
        meta: bool = False,
    ) -> None:
        self._require_lane(from_lane)
        self._require_lane(to_lane)
        self._grants.append(
            LaneGrant(
                from_lane=from_lane,
                to_lane=to_lane,
                keys=list(keys or []),
                meta=meta,
            )
        )

    def open_run(
        self,
        lane_id: str,
        run_id: str,
        *,
        started_at: datetime | None = None,
        meta: Mapping[str, Any] | None = None,
    ) -> WalkBag:
        self._require_lane(lane_id)
        existing = self._find_run(lane_id, run_id)
        if existing is not None:
            if meta:
                existing.meta.update(dict(meta))
            return existing.bag
        stamp = _as_utc(started_at or datetime.now(timezone.utc))
        record = _LaneRun(
            run_id=run_id,
            started_at=stamp,
            meta=dict(meta or {}),
        )
        self._runs[lane_id].append(record)
        return record.bag

    def put(self, lane_id: str, run_id: str, key: str, value: Any) -> None:
        run = self._find_run(lane_id, run_id)
        if run is None:
            raise IsolationViolation(
                f"run {run_id!r} is not open on lane {lane_id!r}"
            )
        run.bag.put(key, value)

    def handoff(self, from_lane: str, to_lane: str, handoff: HandoffRecord) -> None:
        """One-shot share of named evidence refs from publisher to caller lane."""
        self._require_lane(from_lane)
        self._require_lane(to_lane)
        visible = self._handoff_keys.setdefault((to_lane, from_lane), set())
        for ref in handoff.evidence_refs:
            if not self._publisher_has_key(from_lane, ref):
                raise IsolationViolation(
                    f"lane {from_lane!r} cannot hand off unreadable {ref!r}"
                )
            visible.add(ref)

    def observe(
        self,
        caller_lane: str,
        target_lane: str,
        *,
        selector: ObserveSelector,
        key: str | None = None,
        meta: bool = False,
    ) -> ObserveResult:
        """Authorized cross-run read (JL-05..07). Exactly one of ``key`` / ``meta``."""
        if (key is None) == (not meta):
            if key is not None and meta:
                return ObserveResult(
                    status="denied",
                    reason="observe needs exactly one of key or meta",
                )
            return ObserveResult(
                status="denied",
                reason="observe needs exactly one of key or meta",
            )
        self._require_lane(caller_lane)
        self._require_lane(target_lane)
        run = self._resolve_run(target_lane, selector)
        if run is None:
            return ObserveResult(status="denied", reason="no matching run")
        if meta:
            if not self._may_observe_meta(caller_lane, target_lane):
                return ObserveResult(
                    status="denied",
                    reason="meta not exposed to caller",
                    run_id=run.run_id,
                )
            return ObserveResult(
                status="ok",
                run_id=run.run_id,
                meta={
                    "run_id": run.run_id,
                    "started_at": run.started_at.isoformat().replace("+00:00", "Z"),
                    **run.meta,
                },
            )
        assert key is not None
        if not self._may_observe_key(caller_lane, target_lane, key):
            return ObserveResult(
                status="denied",
                reason="key not exposed to caller",
                run_id=run.run_id,
            )
        if key not in run.bag:
            return ObserveResult(
                status="denied",
                reason=f"key {key!r} missing on run",
                run_id=run.run_id,
            )
        return ObserveResult(
            status="ok",
            run_id=run.run_id,
            value=_serialize_value(run.bag.get(key)),
        )

    def _may_observe_meta(self, caller_lane: str, target_lane: str) -> bool:
        if caller_lane == target_lane:
            return True
        lane = self._lanes[target_lane]
        if _exposure_allows(lane.meta, caller_lane):
            return True
        if (caller_lane, target_lane) in self._handoff_meta:
            return True
        return any(
            g.from_lane == target_lane and g.to_lane == caller_lane and g.meta
            for g in self._grants
        )

    def _may_observe_key(self, caller_lane: str, target_lane: str, key: str) -> bool:
        if caller_lane == target_lane:
            return True
        lane = self._lanes[target_lane]
        rule = lane.keys.get(key)
        if rule is not None and _exposure_allows(rule, caller_lane):
            return True
        if key in self._handoff_keys.get((caller_lane, target_lane), set()):
            return True
        return any(
            g.from_lane == target_lane
            and g.to_lane == caller_lane
            and key in g.keys
            for g in self._grants
        )

    def _publisher_has_key(self, lane_id: str, key: str) -> bool:
        for run in self._runs.get(lane_id, []):
            if key in run.bag:
                return True
        return False

    def _require_lane(self, lane_id: str) -> None:
        if lane_id not in self._lanes:
            raise IsolationViolation(f"lane {lane_id!r} is not registered")

    def _find_run(self, lane_id: str, run_id: str) -> _LaneRun | None:
        for run in self._runs.get(lane_id, []):
            if run.run_id == run_id:
                return run
        return None

    def _resolve_run(
        self, lane_id: str, selector: ObserveSelector
    ) -> _LaneRun | None:
        runs = self._runs.get(lane_id, [])
        if not runs:
            return None
        if selector.run_id is not None:
            return self._find_run(lane_id, selector.run_id)
        if selector.latest:
            return runs[-1]
        if selector.before is not None:
            bound = parse_iso_timestamp(selector.before)
            if bound is None:
                return None
            bound = _as_utc(bound)
            eligible = [r for r in runs if r.started_at < bound]
            return eligible[-1] if eligible else None
        if selector.at_or_before is not None:
            bound = parse_iso_timestamp(selector.at_or_before)
            if bound is None:
                return None
            bound = _as_utc(bound)
            eligible = [r for r in runs if r.started_at <= bound]
            return eligible[-1] if eligible else None
        return None


def job_lane_broker_from_mapping(
    job_lanes: Mapping[str, Any] | None,
    lane_grants: list[Mapping[str, Any]] | None = None,
) -> JobLaneBroker:
    """Build a broker catalog from story ``environment.job_lanes`` YAML."""
    lanes: dict[str, JobLane] = {}
    for lane_id, raw in (job_lanes or {}).items():
        body = dict(raw or {})
        body["lane_id"] = lane_id
        lanes[lane_id] = JobLane.model_validate(body)
    broker = JobLaneBroker(lanes=lanes)
    for raw_grant in lane_grants or []:
        grant = LaneGrant.model_validate(dict(raw_grant))
        broker.grant(
            from_lane=grant.from_lane,
            to_lane=grant.to_lane,
            keys=list(grant.keys),
            meta=grant.meta,
        )
    return broker


__all__ = [
    "ExposureMode",
    "ExposureRule",
    "IsolationViolation",
    "JobLane",
    "JobLaneBroker",
    "LaneGrant",
    "ObserveResult",
    "ObserveSelector",
    "ObserveStatus",
    "job_lane_broker_from_mapping",
]
