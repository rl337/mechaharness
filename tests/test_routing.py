"""Decision-plane surface and shadow backend tests."""

from __future__ import annotations

import pytest

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
    hash_state,
)
from mechaharness.judgement_policy import JudgementFacts, JudgementPolicy, JudgementThreshold
from mechaharness.routing import (
    ShadowJudgeLog,
    activate_scoped_policy,
    route_at_boundary,
    shadow_decision_backends,
    shadow_judge,
)


@pytest.mark.asyncio
async def test_shadow_judge_does_not_require_activation() -> None:
    log = ShadowJudgeLog()
    provider = FixtureJudgeProvider({"e": {"p_true": 0.4}})
    req = JudgeRequest(
        state="s",
        state_hash=hash_state("s"),
        questions=[NoulQuestion(id="e", instructions="?")],
        question_set_version="v1",
    )
    result = await shadow_judge(req, provider=provider, log=log, activate=False)
    assert result.answers
    assert log.entries[0]["activated"] is False


def test_route_at_boundary_logs_candidates() -> None:
    decision = route_at_boundary(boundary="task_entry", task_kind="judge")
    assert decision.selected.lane == "judge"
    assert len(decision.candidates) >= 2
    assert any(c.lane == "reason" for c in decision.candidates)


def test_activate_scoped_policy_requires_calibration() -> None:
    policy = JudgementPolicy(
        version="v1",
        thresholds=[JudgementThreshold(signal_id="e", allow_above=0.5)],
    )
    assert (
        activate_scoped_policy(
            facts=JudgementFacts(),
            signals=[NoulSignal(id="e", p_true=0.9)],
            policy=policy,
            calibrated=False,
        )
        is None
    )
    verdict = activate_scoped_policy(
        facts=JudgementFacts(),
        signals=[NoulSignal(id="e", p_true=0.9)],
        policy=policy,
        calibrated=True,
    )
    assert verdict is not None
    assert verdict.kind == "ALLOW"


@pytest.mark.asyncio
async def test_rules_decision_surface_and_invalid_choice() -> None:
    backend = RulesDecisionBackend({"route": "billing"})
    surface = DecisionSurface(
        kind="choice",
        question=ChoiceQuestion(
            id="route",
            instructions="?",
            options=[
                ChoiceOption(id="billing", description="b"),
                ChoiceOption(id="other", description="o"),
            ],
        ),
        allowed_actions=["billing"],
    )
    result = await backend.evaluate(surface, state={})
    assert result.rejected is False
    bad = reject_invalid_choice(
        ChoiceSignal(id="route", selected="other", probabilities={"other": 1.0}),
        ["billing"],
    )
    assert bad.rejected is True


def test_shadow_decision_backends_marks_unavailable() -> None:
    report = shadow_decision_backends(
        state_hash="h1",
        candidate_actions=["allow", "deny"],
        evidence_refs=["obs:1"],
        backends={
            "rules": {
                "available": True,
                "latency_ms": 1.0,
                "verified_success": 0.9,
                "whole_task_cost": 0.1,
            },
            "systemone": {"available": False, "exclusion_reason": "lane_not_loaded"},
        },
    )
    by_kind = {c.kind: c for c in report.candidates}
    assert by_kind["rules"].available is True
    assert by_kind["systemone"].available is False
    assert by_kind["systemone"].latency_ms is None
