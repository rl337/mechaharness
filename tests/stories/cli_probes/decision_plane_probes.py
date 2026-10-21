"""CLI probes for former ``decision_plane`` op-dispatch stories."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.decision_log import (
    DecisionRecord,
    export_offline_dataset,
    replay_verdict,
)
from mechaharness.decision_plane_runtime import (
    build_decision_plane_telemetry,
    compare_shadow_decision,
)
from mechaharness.decision_surfaces import (
    DecisionSurface,
    RulesDecisionBackend,
    reject_invalid_choice,
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


__all__ = [
    "DecisionPlaneShadowCompareCommand",
    "DecisionSurfaceRejectCommand",
    "FixtureJudgeBatchCommand",
    "OfflineDecisionExportCommand",
    "PolicyReplayCommand",
    "run_decision_plane_shadow_compare",
    "run_decision_surface_reject",
    "run_fixture_judge_batch",
    "run_offline_decision_export",
    "run_policy_replay",
]
