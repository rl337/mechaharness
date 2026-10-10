"""Runtime helpers for the ``decision_plane`` Agentic Recipe (DP-01..09).

Graph structure lives in :mod:`mechaharness.graph_templates.decision_plane`.
This module owns projection, batched evidence collection, deterministic policy,
shadow comparison, and evaluation-ready telemetry — without a second executor.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.decision_surfaces import (
    DecisionSurface,
    DecisionSurfaceResult,
    RulesDecisionBackend,
    reject_invalid_choice,
)
from mechaharness.inference.judge import (
    ChoiceOption,
    ChoiceQuestion,
    ChoiceSignal,
    NoulQuestion,
    Question,
    ScoreQuestion,
    ScoreSignal,
    Signal,
)

EscalationReason = Literal[
    "confidence_below_floor",
    "choice_not_allowed",
    "invalid_output",
    "policy_disagreement",
    "unresolved",
]


class DecisionPlaneProjection(BaseModel):
    """Deliberate structured state for a decision (DP-01)."""

    model_config = ConfigDict(extra="allow")

    state: dict[str, Any] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)
    facts_fingerprint: str = ""
    projection_fingerprint: str = ""


class DecisionPlanePolicyResult(BaseModel):
    """Deterministic final action or routable escalation (DP-04 / DP-06)."""

    model_config = ConfigDict(extra="allow")

    final_action: str | None = None
    escalate: bool = False
    escalation_reason: EscalationReason | str | None = None
    escalation_route: str = "host_policy"
    signals: dict[str, Any] = Field(default_factory=dict)
    rejected: list[str] = Field(default_factory=list)
    confidence: float | None = None
    batch_invocation_count: int = 1


class ShadowDecisionComparison(BaseModel):
    """Production-controlled path with recorded shadow candidate (DP-07)."""

    model_config = ConfigDict(extra="allow")

    production: DecisionPlanePolicyResult
    shadow: DecisionPlanePolicyResult | None = None
    shadow_controls_execution: bool = False
    agreement: bool | None = None
    shadow_unavailable: bool = False


class DecisionPlaneTelemetry(BaseModel):
    """Evaluation-ready decision record without raw sensitive context (DP-08)."""

    model_config = ConfigDict(extra="allow")

    recipe: str = "decision_plane"
    question_schema_ids: list[str] = Field(default_factory=list)
    projection_fingerprint: str | None = None
    facts_fingerprint: str | None = None
    model_ref: str | None = None
    typed_answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    final_action: str | None = None
    escalation_reason: str | None = None
    escalation_route: str | None = None
    shadow_action: str | None = None
    later_outcome: str | None = None
    latency_ms: float | None = None
    usage: dict[str, Any] = Field(default_factory=dict)


def _fingerprint(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def project_decision_state(
    raw_context: Mapping[str, Any],
    *,
    project_keys: Sequence[str],
    facts: Mapping[str, Any] | None = None,
) -> DecisionPlaneProjection:
    """Build a deliberate projection + facts without model inference (DP-01/03)."""
    state = {k: raw_context[k] for k in project_keys if k in raw_context}
    fact_map = dict(facts or {})
    return DecisionPlaneProjection(
        state=state,
        facts=fact_map,
        facts_fingerprint=_fingerprint(fact_map),
        projection_fingerprint=_fingerprint(state),
    )


def question_from_spec(spec: Mapping[str, Any]) -> Question:
    """Parse a recipe question dict into a typed judge Question."""
    kind = str(spec.get("kind") or "choice")
    qid = str(spec["id"])
    instructions = str(
        spec.get("instructions") or spec.get("prompt") or spec.get("label") or qid
    )
    if kind == "choice":
        options_raw = list(spec.get("options") or [])
        options: list[ChoiceOption] = []
        for opt in options_raw:
            if isinstance(opt, Mapping):
                options.append(
                    ChoiceOption(
                        id=str(opt["id"]),
                        description=str(
                            opt.get("description") or opt.get("label") or opt["id"]
                        ),
                    )
                )
            else:
                options.append(ChoiceOption(id=str(opt), description=str(opt)))
        return ChoiceQuestion(id=qid, instructions=instructions, options=options)
    if kind == "score":
        return ScoreQuestion(
            id=qid,
            instructions=instructions,
            min=float(spec.get("min", 0.0)),
            max=float(spec.get("max", 1.0)),
        )
    if kind == "noul":
        return NoulQuestion(id=qid, instructions=instructions)
    raise ValueError(f"unsupported decision question kind {kind!r}")


def surfaces_from_questions(questions: Sequence[Mapping[str, Any]]) -> list[DecisionSurface]:
    surfaces: list[DecisionSurface] = []
    for spec in questions:
        q = question_from_spec(spec)
        kind = str(spec.get("kind") or "choice")
        allowed = [str(a) for a in list(spec.get("allowed_actions") or [])]
        surfaces.append(
            DecisionSurface(
                kind="choice" if kind == "choice" else "score" if kind == "score" else "noul",
                question=q,
                allowed_actions=allowed,
            )
        )
    return surfaces


async def evaluate_decision_batch(
    questions: Sequence[Mapping[str, Any]],
    *,
    answers: Mapping[str, Any],
    state: Mapping[str, Any] | None = None,
    backend: RulesDecisionBackend | None = None,
) -> tuple[list[DecisionSurfaceResult], int]:
    """Answer multiple compatible questions in one logical invocation (DP-02)."""
    runner = backend or RulesDecisionBackend(answers=answers)
    results: list[DecisionSurfaceResult] = []
    # One backend object + one answers map = one batch invocation for DI tests.
    invocation_count = 1
    for surface in surfaces_from_questions(questions):
        result = await runner.evaluate(surface, state=state or {})
        if (
            isinstance(surface.question, ChoiceQuestion)
            and surface.allowed_actions
            and isinstance(result.signal, ChoiceSignal)
        ):
            checked = reject_invalid_choice(result.signal, surface.allowed_actions)
            if checked.rejected:
                result = checked
        results.append(result)
    return results, invocation_count


def apply_decision_plane_policy(
    results: Sequence[DecisionSurfaceResult],
    *,
    questions: Sequence[Mapping[str, Any]],
    confidence: float | None,
    confidence_floor: float,
    escalation_route: str = "host_policy",
    action_question_id: str = "team",
    batch_invocation_count: int = 1,
) -> DecisionPlanePolicyResult:
    """Code-owned final action; escalate on confidence/validity (DP-04/05/06)."""
    signals: dict[str, Any] = {}
    rejected: list[str] = []
    for result in results:
        sid = getattr(result.signal, "id", None)
        if sid is None:
            continue
        if isinstance(result.signal, ChoiceSignal):
            signals[str(sid)] = result.signal.selected
        elif isinstance(result.signal, ScoreSignal):
            signals[str(sid)] = result.signal.value
        else:
            signals[str(sid)] = result.signal.model_dump(mode="json")
        if result.rejected:
            rejected.append(str(sid))

    if rejected:
        return DecisionPlanePolicyResult(
            escalate=True,
            escalation_reason="choice_not_allowed",
            escalation_route=escalation_route,
            signals=signals,
            rejected=rejected,
            confidence=confidence,
            batch_invocation_count=batch_invocation_count,
        )
    if confidence is not None and confidence < confidence_floor:
        return DecisionPlanePolicyResult(
            escalate=True,
            escalation_reason="confidence_below_floor",
            escalation_route=escalation_route,
            signals=signals,
            confidence=confidence,
            batch_invocation_count=batch_invocation_count,
        )

    action = signals.get(action_question_id)
    envelopes = {
        str(q["id"]): [str(a) for a in list(q.get("allowed_actions") or [])]
        for q in questions
        if isinstance(q, Mapping) and q.get("id")
    }
    allowed = envelopes.get(action_question_id) or []
    if action is not None and allowed and str(action) not in allowed:
        return DecisionPlanePolicyResult(
            escalate=True,
            escalation_reason="choice_not_allowed",
            escalation_route=escalation_route,
            signals=signals,
            rejected=[action_question_id],
            confidence=confidence,
            batch_invocation_count=batch_invocation_count,
        )
    return DecisionPlanePolicyResult(
        final_action=str(action) if action is not None else None,
        escalate=False,
        signals=signals,
        confidence=confidence,
        batch_invocation_count=batch_invocation_count,
    )


async def run_decision_plane_policy(
    *,
    questions: Sequence[Mapping[str, Any]],
    answers: Mapping[str, Any],
    confidence: float | None,
    confidence_floor: float,
    escalation_route: str = "host_policy",
    state: Mapping[str, Any] | None = None,
    action_question_id: str = "team",
) -> DecisionPlanePolicyResult:
    results, invocations = await evaluate_decision_batch(
        questions, answers=answers, state=state
    )
    return apply_decision_plane_policy(
        results,
        questions=questions,
        confidence=confidence,
        confidence_floor=confidence_floor,
        escalation_route=escalation_route,
        action_question_id=action_question_id,
        batch_invocation_count=invocations,
    )


def assemble_context_within_budget(
    candidates: Sequence[Mapping[str, Any]],
    *,
    token_budget: int,
    min_relevance: float = 0.0,
    min_trust: float = 0.0,
    min_freshness: float = 0.0,
) -> list[str]:
    """Deterministically pack scored retrieval candidates into a token budget.

    Judge scores are inputs only. Thresholds and packing order are owned by
    caller policy (DP-04). Candidates with missing numeric fields are skipped.
    """
    scored: list[tuple[float, float, float, int, str]] = []
    for raw in candidates:
        try:
            relevance = float(raw["relevance"])
            trust = float(raw["trust"])
            freshness = float(raw["freshness"])
            tokens = int(raw["tokens"])
            cid = str(raw["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if tokens <= 0:
            continue
        if relevance < min_relevance or trust < min_trust or freshness < min_freshness:
            continue
        scored.append((relevance, trust, freshness, tokens, cid))
    scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    selected: list[str] = []
    used = 0
    for _rel, _trust, _fresh, tokens, cid in scored:
        if used + tokens > token_budget:
            continue
        selected.append(cid)
        used += tokens
    return selected


async def compare_shadow_decision(
    *,
    questions: Sequence[Mapping[str, Any]],
    production_answers: Mapping[str, Any],
    shadow_answers: Mapping[str, Any] | None,
    confidence: float | None,
    confidence_floor: float,
    escalation_route: str = "host_policy",
) -> ShadowDecisionComparison:
    """Record candidate vs production; production always controls (DP-07)."""
    production = await run_decision_plane_policy(
        questions=questions,
        answers=production_answers,
        confidence=confidence,
        confidence_floor=confidence_floor,
        escalation_route=escalation_route,
    )
    if shadow_answers is None:
        return ShadowDecisionComparison(
            production=production,
            shadow=None,
            shadow_controls_execution=False,
            agreement=None,
            shadow_unavailable=True,
        )
    shadow = await run_decision_plane_policy(
        questions=questions,
        answers=shadow_answers,
        confidence=confidence,
        confidence_floor=confidence_floor,
        escalation_route=escalation_route,
    )
    agreement = production.final_action == shadow.final_action and (
        production.escalate == shadow.escalate
    )
    return ShadowDecisionComparison(
        production=production,
        shadow=shadow,
        shadow_controls_execution=False,
        agreement=agreement,
        shadow_unavailable=False,
    )


def build_decision_plane_telemetry(
    *,
    questions: Sequence[Mapping[str, Any]],
    projection: DecisionPlaneProjection | None = None,
    policy: DecisionPlanePolicyResult | None = None,
    shadow: ShadowDecisionComparison | None = None,
    model_ref: str | None = None,
    latency_ms: float | None = None,
    usage: Mapping[str, Any] | None = None,
    later_outcome: str | None = None,
    raw_context: Mapping[str, Any] | None = None,
) -> DecisionPlaneTelemetry:
    """Aggregate metrics; never require raw sensitive context (DP-08)."""
    _ = raw_context  # explicitly unused — callers may pass it; we do not emit it
    typed: dict[str, Any] = {}
    if policy is not None:
        typed = dict(policy.signals)
    shadow_action = None
    if shadow is not None and shadow.shadow is not None:
        shadow_action = shadow.shadow.final_action
    return DecisionPlaneTelemetry(
        question_schema_ids=[str(q.get("id")) for q in questions if q.get("id")],
        projection_fingerprint=projection.projection_fingerprint if projection else None,
        facts_fingerprint=projection.facts_fingerprint if projection else None,
        model_ref=model_ref,
        typed_answers=typed,
        confidence=policy.confidence if policy else None,
        final_action=policy.final_action if policy else None,
        escalation_reason=(
            str(policy.escalation_reason)
            if policy and policy.escalation_reason is not None
            else None
        ),
        escalation_route=policy.escalation_route if policy and policy.escalate else None,
        shadow_action=shadow_action,
        later_outcome=later_outcome,
        latency_ms=latency_ms,
        usage=dict(usage or {}),
    )


def signal_to_public(signal: Signal) -> Any:
    if isinstance(signal, ChoiceSignal):
        return signal.selected
    if isinstance(signal, ScoreSignal):
        return signal.value
    return signal.model_dump(mode="json")
