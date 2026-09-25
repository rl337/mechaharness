"""Shadow judge collection and deterministic routing (RTE-* / Phase 2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.environment import LANE_JUDGE, LANE_MEDIA, LANE_REASON
from mechaharness.inference.judge import Judgement, JudgeProvider, JudgeRequest, judge
from mechaharness.judgement_policy import JudgementFacts, JudgementPolicy, Verdict, decide

Lane = str


class RouteCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    lane: Lane
    profile_hint: str
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    selected: RouteCandidate
    candidates: list[RouteCandidate] = Field(default_factory=list)
    boundary: str = "task_entry"


@dataclass
class ShadowJudgeLog:
    """Collect judge results without changing production actions."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def append(self, *, request: JudgeRequest, result: Judgement, activated: bool) -> None:
        self.entries.append(
            {
                "trace_id": request.trace_id,
                "state_hash": request.state_hash,
                "question_set_version": request.question_set_version,
                "activated": activated,
                "answer_ids": [a.id for a in result.answers],
                "errors": [e.model_dump(by_alias=True) for e in result.errors],
                "latency_ms": result.usage.latency_ms,
            }
        )


async def shadow_judge(
    request: JudgeRequest,
    *,
    provider: JudgeProvider,
    log: ShadowJudgeLog,
    activate: bool = False,
) -> Judgement:
    """Run judge in shadow mode; production action change only when ``activate``."""
    result = await judge(request, provider=provider)
    log.append(request=request, result=result, activated=activate)
    return result


def route_at_boundary(
    *,
    boundary: str,
    task_kind: Literal["chat", "judge", "media", "tool"] | str,
    available_lanes: Sequence[Lane] | None = None,
    prefer: Lane | None = None,
) -> RouteDecision:
    """Deterministic routing at task/phase boundaries (RTE-01/03)."""
    available = list(available_lanes or [LANE_REASON, LANE_JUDGE, LANE_MEDIA])
    hints = {
        LANE_REASON: "infer load reason-fast",
        LANE_JUDGE: "infer load decide-fast",
        LANE_MEDIA: "infer load media",
    }
    preferred_by_kind = {
        "chat": LANE_REASON,
        "judge": LANE_JUDGE,
        "decide": LANE_JUDGE,  # legacy task_kind alias
        "media": LANE_MEDIA,
        "tool": LANE_REASON,
    }
    target = prefer or preferred_by_kind.get(task_kind, LANE_REASON)
    candidates: list[RouteCandidate] = []
    for lane in available:
        score = 1.0 if lane == target else 0.0
        candidates.append(
            RouteCandidate(
                lane=lane,
                profile_hint=hints.get(lane, f"infer load <{lane}>"),
                score=score,
                reasons=[f"task_kind={task_kind}", f"boundary={boundary}"],
            )
        )
    candidates.sort(key=lambda c: c.score, reverse=True)
    selected = candidates[0] if candidates else RouteCandidate(
        lane=target,
        profile_hint=hints.get(target, f"infer load <{target}>"),
        score=1.0,
        reasons=["fallback"],
    )
    return RouteDecision(selected=selected, candidates=candidates, boundary=boundary)


def activate_scoped_policy(
    *,
    facts: JudgementFacts | Mapping[str, Any],
    signals: Sequence[Any],
    policy: JudgementPolicy | Mapping[str, Any],
    calibrated: bool,
) -> Verdict | None:
    """Activate judgement policy only when declared calibration criteria are met."""
    if not calibrated:
        return None
    return decide(facts, signals, policy)


DecisionBackendKind = Literal[
    "rules", "small_local", "reason_adapter", "systemone", "hybrid"
]


@dataclass
class DecisionBackendCandidate:
    kind: DecisionBackendKind
    available: bool
    latency_ms: float | None = None
    decision_error: float | None = None
    verified_success: float | None = None
    whole_task_cost: float | None = None
    exclusion_reason: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class DecisionBackendShadowReport:
    """RTE-01/02 shadow comparison on matched decision obligations."""

    state_hash: str
    candidates: list[DecisionBackendCandidate]
    matched_inputs: dict[str, Any]
    baseline_kind: DecisionBackendKind = "rules"


def shadow_decision_backends(
    *,
    state_hash: str,
    candidate_actions: Sequence[str],
    evidence_refs: Sequence[str],
    backends: Mapping[DecisionBackendKind, Mapping[str, Any]],
) -> DecisionBackendShadowReport:
    """Compare decision backends; unavailable → marked, never synthetic results."""
    rows: list[DecisionBackendCandidate] = []
    for kind, meta in backends.items():
        available = bool(meta.get("available", False))
        if not available:
            rows.append(
                DecisionBackendCandidate(
                    kind=kind,
                    available=False,
                    exclusion_reason=str(meta.get("exclusion_reason", "unavailable")),
                )
            )
            continue
        rows.append(
            DecisionBackendCandidate(
                kind=kind,
                available=True,
                latency_ms=float(meta["latency_ms"]) if "latency_ms" in meta else None,
                decision_error=(
                    float(meta["decision_error"]) if "decision_error" in meta else None
                ),
                verified_success=(
                    float(meta["verified_success"])
                    if "verified_success" in meta
                    else None
                ),
                whole_task_cost=(
                    float(meta["whole_task_cost"])
                    if "whole_task_cost" in meta
                    else None
                ),
                notes=list(meta.get("notes", [])),
            )
        )
    return DecisionBackendShadowReport(
        state_hash=state_hash,
        candidates=rows,
        matched_inputs={
            "candidate_actions": list(candidate_actions),
            "evidence_refs": list(evidence_refs),
        },
    )
