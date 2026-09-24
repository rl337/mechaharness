"""Shadow judge and deterministic routing tests."""

from __future__ import annotations

import pytest

from mechaharness.inference.judge import (
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
