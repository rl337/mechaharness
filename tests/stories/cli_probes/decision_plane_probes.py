"""CLI probes for former ``decision_plane`` op-dispatch stories."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.access import AccessPolicy
from mechaharness.decision_log import (
    DecisionRecord,
    export_offline_dataset,
    replay_verdict,
)
from mechaharness.decision_plane_runtime import (
    assemble_context_within_budget,
    build_decision_plane_telemetry,
    compare_shadow_decision,
    project_decision_state,
    run_decision_plane_policy,
)
from mechaharness.decision_surfaces import (
    DecisionSurface,
    RulesDecisionBackend,
    reject_invalid_choice,
)
from mechaharness.graph_templates import (
    DecisionPlaneTemplate,
    GraphTemplateParams,
    IndependentReviewTemplate,
)
from mechaharness.inference.judge import (
    ChoiceOption,
    ChoiceQuestion,
    ChoiceSignal,
    FixtureJudgeProvider,
    JudgeRequest,
    NoulQuestion,
    NoulSignal,
    ScoreAnchor,
    ScoreQuestion,
    hash_state,
    judge,
)
from mechaharness.judgement_policy import (
    JudgementFacts,
    JudgementPolicy,
    JudgementThreshold,
)


def _build_questions(raw: list[dict[str, Any]]) -> list[Any]:
    out: list[Any] = []
    for item in raw:
        kind = item["kind"]
        if kind == "choice":
            out.append(
                ChoiceQuestion(
                    id=item["id"],
                    instructions=item.get("instructions", ""),
                    options=[
                        ChoiceOption(
                            id=o["id"], description=o.get("description", "")
                        )
                        for o in item["options"]
                    ],
                )
            )
        elif kind == "noul":
            out.append(
                NoulQuestion(id=item["id"], instructions=item.get("instructions", ""))
            )
        elif kind == "score":
            out.append(
                ScoreQuestion(
                    id=item["id"],
                    instructions=item.get("instructions", ""),
                    min=float(item.get("min", 0.0)),
                    max=float(item.get("max", 1.0)),
                    anchors=[
                        ScoreAnchor(
                            value=float(a["value"]),
                            description=a.get("description", ""),
                        )
                        for a in item.get("anchors", [])
                    ],
                )
            )
        else:
            raise ValueError(f"unsupported question kind {kind!r}")
    return out


class FixtureJudgeBatchCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Any
    questions: list[dict[str, Any]]
    answers: dict[str, Any] = Field(default_factory=dict)
    question_set_version: str = "lab"


async def run_fixture_judge_batch(body: FixtureJudgeBatchCommand) -> dict[str, Any]:
    judgement = await judge(
        JudgeRequest(
            state=body.state,
            state_hash=hash_state(body.state),
            questions=_build_questions(body.questions),
            question_set_version=body.question_set_version,
        ),
        provider=FixtureJudgeProvider(body.answers),
    )
    return {
        "answer_count": len(judgement.answers),
        "error_count": len(judgement.errors),
        "answer_ids": sorted(a.id for a in judgement.answers),
    }


class DecisionSurfaceRejectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: dict[str, Any]
    allowed_actions: list[str] = Field(default_factory=list)
    answers: dict[str, Any] = Field(default_factory=dict)
    invalid_choice: str
    state: dict[str, Any] = Field(default_factory=dict)


async def run_decision_surface_reject(
    body: DecisionSurfaceRejectCommand,
) -> dict[str, Any]:
    questions = _build_questions([body.question])
    surface = DecisionSurface(
        kind="choice",
        question=questions[0],
        allowed_actions=list(body.allowed_actions),
    )
    backend_rules = RulesDecisionBackend(body.answers)
    result = await backend_rules.evaluate(surface, state=body.state)
    invalid = reject_invalid_choice(
        ChoiceSignal(
            id=surface.question.id,
            selected=body.invalid_choice,
            probabilities={body.invalid_choice: 1.0},
        ),
        body.allowed_actions,
    )
    return {
        "rules_rejected": result.rejected,
        "invalid_choice_rejected": invalid.rejected,
        "rules_source": result.source,
    }


class OfflineDecisionExportCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[dict[str, Any]] = Field(default_factory=list)
    split: str = "train"
    include_outcomes: bool = False


def run_offline_decision_export(body: OfflineDecisionExportCommand) -> dict[str, Any]:
    records = [DecisionRecord.model_validate(r) for r in body.records]
    export = export_offline_dataset(
        records,
        split=body.split,
        include_outcomes=body.include_outcomes,
    )
    outcome_ids = [r.get("outcomeId") for r in export.records]
    return {
        "record_count": len(export.records),
        "outcomes_leaked": any(oid is not None for oid in outcome_ids),
        "lineage": list(export.lineage),
        "split": export.split,
    }


class PolicyReplayCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")


def run_policy_replay(body: PolicyReplayCommand) -> dict[str, Any]:
    del body
    policy = JudgementPolicy(
        version="story-replay",
        thresholds=[JudgementThreshold(signal_id="e", allow_above=0.5)],
    )
    verdict = replay_verdict(
        facts=JudgementFacts(action="noop"),
        signals=[NoulSignal(id="e", p_true=0.9)],
        policy=policy,
    )
    return {"verdict_kind": verdict.kind}


class DecisionPlaneRecipeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = "decision_plane"
    state_projection: dict[str, Any] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    confidence_floor: float = 0.7
    shadow_mode: bool = False


def run_decision_plane_recipe(body: DecisionPlaneRecipeCommand) -> dict[str, Any]:
    graph = DecisionPlaneTemplate().instantiate(
        GraphTemplateParams(
            goal=body.goal,
            inputs={
                "state_projection": dict(body.state_projection),
                "facts": dict(body.facts),
                "questions": list(body.questions),
                "confidence_floor": body.confidence_floor,
                "shadow_mode": body.shadow_mode,
            },
        )
    )
    ask = graph.nodes["ask_batch"]
    project = graph.nodes["project_state"]
    return {
        "template_name": graph.template_name,
        "nodes": sorted(graph.nodes),
        "ask_batch_question_count": len(ask.payload.get("questions") or []),
        "facts_on_project_not_ask": "facts" in project.payload
        and "facts" not in ask.payload,
        "confidence_floor": ask.payload.get("confidence_floor"),
    }


class DecisionPlaneProjectionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_context: dict[str, Any] = Field(default_factory=dict)
    project_keys: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)


def run_decision_plane_projection(
    body: DecisionPlaneProjectionCommand,
) -> dict[str, Any]:
    proj = project_decision_state(
        dict(body.raw_context),
        project_keys=list(body.project_keys),
        facts=dict(body.facts),
    )
    return {
        "projection": proj.state,
        "facts": list(proj.facts),
        "projection_has_secret": "secret" in proj.state,
        "no_model_invocation": True,
        "facts_fingerprint_nonempty": bool(proj.facts_fingerprint),
    }


class DecisionPlanePolicyCaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[dict[str, Any]] = Field(default_factory=list)
    escalation_route: str = "host_policy"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7
    action_question_id: str | None = None


async def run_decision_plane_policy_case(
    body: DecisionPlanePolicyCaseCommand,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "questions": list(body.questions),
        "answers": dict(body.answers),
        "confidence": body.confidence,
        "confidence_floor": body.confidence_floor,
        "escalation_route": body.escalation_route,
    }
    if body.action_question_id is not None:
        kwargs["action_question_id"] = body.action_question_id
    result = await run_decision_plane_policy(**kwargs)
    return {
        "final_action": result.final_action,
        "escalate": result.escalate,
        "escalation_reason": result.escalation_reason,
        "escalation_route": result.escalation_route,
        "batch_invocation_count": result.batch_invocation_count,
    }


class DecisionPlaneShadowCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[dict[str, Any]] = Field(default_factory=list)
    production_answers: dict[str, Any] = Field(default_factory=dict)
    shadow_answers: dict[str, Any] | None = None
    confidence: float | None = None
    confidence_floor: float = 0.7


async def run_decision_plane_shadow(
    body: DecisionPlaneShadowCommand,
) -> dict[str, Any]:
    cmp = await compare_shadow_decision(
        questions=list(body.questions),
        production_answers=dict(body.production_answers),
        shadow_answers=body.shadow_answers,
        confidence=body.confidence,
        confidence_floor=body.confidence_floor,
    )
    return {
        "production_action": cmp.production.final_action,
        "shadow_controls_execution": cmp.shadow_controls_execution,
        "both_outcomes_recorded": cmp.shadow is not None,
        "agreement": cmp.agreement,
        "shadow_unavailable": cmp.shadow_unavailable,
        "shadow_action": cmp.shadow.final_action if cmp.shadow is not None else None,
    }


class DecisionPlaneTelemetryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[dict[str, Any]] = Field(default_factory=list)
    state_projection: dict[str, Any] = Field(default_factory=dict)
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    final_action: str | None = None
    model_ref: str | None = None
    latency_ms: float | None = None
    raw_body: Any = None


async def run_decision_plane_telemetry(
    body: DecisionPlaneTelemetryCommand,
) -> dict[str, Any]:
    questions = list(body.questions)
    proj = project_decision_state(
        {**dict(body.state_projection), "body": body.raw_body},
        project_keys=list(body.state_projection.keys()),
        facts={},
    )
    policy = await run_decision_plane_policy(
        questions=questions,
        answers=dict(body.answers),
        confidence=body.confidence,
        confidence_floor=0.7,
    )
    if body.final_action and not policy.escalate:
        policy.final_action = body.final_action
    tel = build_decision_plane_telemetry(
        questions=questions,
        projection=proj,
        policy=policy,
        model_ref=body.model_ref,
        latency_ms=body.latency_ms,
        raw_context={"body": body.raw_body},
    )
    dumped = tel.model_dump(mode="json")
    return {
        "has_question_schema_ids": bool(tel.question_schema_ids),
        "has_projection_fingerprint": bool(tel.projection_fingerprint),
        "final_action": tel.final_action,
        "model_ref": tel.model_ref,
        "latency_ms": tel.latency_ms,
        "includes_raw_body": "raw_body" in dumped or "body" in dumped,
    }


class DecisionPlaneModelPolicyCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_projection: dict[str, Any] = Field(default_factory=dict)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    decision_model: Any = None


def run_decision_plane_model_policy(
    body: DecisionPlaneModelPolicyCommand,
) -> dict[str, Any]:
    template = DecisionPlaneTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="model policy",
            inputs={
                "state_projection": dict(body.state_projection),
                "questions": list(body.questions),
            },
            soft_bindings={"decision_model": body.decision_model},
        )
    )
    describe = template.describe()
    return {
        "soft_point_decision_model": any(
            p.get("name") == "decision_model" for p in describe.get("soft_points") or []
        ),
        "ask_model_ref": graph.nodes["ask_batch"].payload.get("model_ref"),
        "describe_has_param_count": "param_count" in describe,
    }


class DecisionPlaneShadowCompareCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[dict[str, Any]] = Field(default_factory=list)
    production_answers: dict[str, Any] = Field(default_factory=dict)
    shadow_answers: dict[str, Any] | None = None
    confidence: float | None = None
    confidence_floor: float = 0.7
    with_telemetry: bool = False


async def run_decision_plane_shadow_compare(
    body: DecisionPlaneShadowCompareCommand,
) -> dict[str, Any]:
    cmp = await compare_shadow_decision(
        questions=list(body.questions),
        production_answers=dict(body.production_answers),
        shadow_answers=body.shadow_answers,
        confidence=body.confidence,
        confidence_floor=body.confidence_floor,
    )
    out: dict[str, Any] = {
        "agreement": cmp.agreement,
        "shadow_unavailable": cmp.shadow_unavailable,
        "production_action": cmp.production.final_action,
    }
    if body.with_telemetry:
        tel = build_decision_plane_telemetry(
            questions=list(body.questions),
            policy=cmp.production,
            shadow=cmp,
        )
        out["telemetry_has_shadow_action"] = tel.shadow_action is not None
    return out


class CitationSupportCaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[dict[str, Any]] = Field(default_factory=list)
    action_question_id: str = "support"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7


async def run_citation_support_case(body: CitationSupportCaseCommand) -> dict[str, Any]:
    result = await run_decision_plane_policy(
        questions=list(body.questions),
        answers=dict(body.answers),
        confidence=body.confidence,
        confidence_floor=body.confidence_floor,
        action_question_id=body.action_question_id,
    )
    claim_verified = not result.escalate and result.final_action == "supported"
    return {
        "claim_verified": claim_verified,
        "escalate": result.escalate,
        "final_action": result.final_action,
    }


class ContextBudgetCaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_budget: int
    min_relevance: float = 0.0
    min_trust: float = 0.0
    min_freshness: float = 0.0
    candidates: list[dict[str, Any]] = Field(default_factory=list)


def run_context_budget_case(body: ContextBudgetCaseCommand) -> dict[str, Any]:
    selected = assemble_context_within_budget(
        list(body.candidates),
        token_budget=body.token_budget,
        min_relevance=body.min_relevance,
        min_trust=body.min_trust,
        min_freshness=body.min_freshness,
    )
    by_id = {str(c["id"]): c for c in body.candidates}
    total = sum(int(by_id[cid]["tokens"]) for cid in selected)
    return {
        "selected_ids": selected,
        "token_total": total,
        "within_budget": total <= body.token_budget,
    }


class RequirementsGapCaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_count: int = 1
    acceptance: list[Any] = Field(default_factory=list)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    action_question_id: str = "coverage"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7
    facts: dict[str, Any] = Field(default_factory=dict)


async def run_requirements_gap_case(
    body: RequirementsGapCaseCommand,
) -> dict[str, Any]:
    review_graph = IndependentReviewTemplate().instantiate(
        GraphTemplateParams(
            goal="requirements review",
            inputs={"reviewer_count": body.reviewer_count},
            acceptance=list(body.acceptance),
        )
    )
    reviews = [n for n in review_graph.nodes if n.startswith("review_")]
    result = await run_decision_plane_policy(
        questions=list(body.questions),
        answers=dict(body.answers),
        confidence=body.confidence,
        confidence_floor=body.confidence_floor,
        action_question_id=body.action_question_id,
    )
    facts = dict(body.facts)
    if result.escalate or result.final_action in {"gap", "unclear"}:
        outcome = "request_tests"
    elif not facts.get("crash_tests_present", True):
        outcome = "request_tests"
    elif result.final_action == "covered":
        outcome = "continue_review"
    else:
        outcome = "request_tests"
    return {
        "template_name": review_graph.template_name,
        "omit_producer_reasoning": review_graph.nodes[reviews[0]].payload.get(
            "omit_producer_reasoning"
        ),
        "outcome": outcome,
        "final_action": result.final_action,
        "escalate": result.escalate,
    }


class TaskRouteCaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[dict[str, Any]] = Field(default_factory=list)
    action_question_id: str = "route"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7
    min_complexity_for_frontier: float = 0.7


async def run_task_route_case(body: TaskRouteCaseCommand) -> dict[str, Any]:
    result = await run_decision_plane_policy(
        questions=list(body.questions),
        answers=dict(body.answers),
        confidence=body.confidence,
        confidence_floor=body.confidence_floor,
        action_question_id=body.action_question_id,
    )
    complexity = float(body.answers.get("complexity") or 0.0)
    final_action = result.final_action
    escalate = result.escalate
    if (
        not escalate
        and final_action == "local_small"
        and complexity >= body.min_complexity_for_frontier
    ):
        final_action = "frontier"
    return {
        "final_action": final_action,
        "escalate": escalate,
    }


class ActionSafetyCaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[dict[str, Any]] = Field(default_factory=list)
    action_question_id: str = "semantic_risk"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7
    grants: list[Any] = Field(default_factory=list)
    required_grants: list[Any] = Field(default_factory=list)


async def run_action_safety_case(body: ActionSafetyCaseCommand) -> dict[str, Any]:
    policy = AccessPolicy(grants=list(body.grants))
    required = list(body.required_grants)
    grants_ok = policy.allows(required) if required else True
    result = await run_decision_plane_policy(
        questions=list(body.questions),
        answers=dict(body.answers),
        confidence=body.confidence,
        confidence_floor=body.confidence_floor,
        action_question_id=body.action_question_id,
    )
    risk = result.final_action
    if not grants_ok:
        decision = "deny"
        hard_won = True
    elif result.escalate or risk == "high":
        decision = "escalate_review"
        hard_won = False
    else:
        decision = "allow"
        hard_won = False
    return {
        "decision": decision,
        "hard_won": hard_won,
        "grants_unchanged": list(policy.grants) == list(body.grants),
        "escalate": result.escalate,
        "final_action": result.final_action,
    }


__all__ = [
    "ActionSafetyCaseCommand",
    "CitationSupportCaseCommand",
    "ContextBudgetCaseCommand",
    "DecisionPlaneModelPolicyCommand",
    "DecisionPlanePolicyCaseCommand",
    "DecisionPlaneProjectionCommand",
    "DecisionPlaneRecipeCommand",
    "DecisionPlaneShadowCommand",
    "DecisionPlaneShadowCompareCommand",
    "DecisionPlaneTelemetryCommand",
    "DecisionSurfaceRejectCommand",
    "FixtureJudgeBatchCommand",
    "OfflineDecisionExportCommand",
    "PolicyReplayCommand",
    "RequirementsGapCaseCommand",
    "TaskRouteCaseCommand",
    "run_action_safety_case",
    "run_citation_support_case",
    "run_context_budget_case",
    "run_decision_plane_model_policy",
    "run_decision_plane_policy_case",
    "run_decision_plane_projection",
    "run_decision_plane_recipe",
    "run_decision_plane_shadow",
    "run_decision_plane_shadow_compare",
    "run_decision_plane_telemetry",
    "run_decision_surface_reject",
    "run_fixture_judge_batch",
    "run_offline_decision_export",
    "run_policy_replay",
    "run_requirements_gap_case",
    "run_task_route_case",
]
