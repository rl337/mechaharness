"""Discriminative-value telemetry for experiment arms (MH-MHRL-15).

Many FineEnvs groups had no reward contrast because every rollout was right or
every rollout was wrong
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#other-things-the-qwen-runs-showed)::

    >>> from mechaharness.discriminative_value import discriminative_report
    >>> from mechaharness.eval_trial import Trial
    >>> report = discriminative_report([
    ...     Trial(trial_id="1", success=True),
    ...     Trial(trial_id="2", success=True),
    ... ])
    >>> report.all_success_tie
    True
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.eval_evidence import Claim
from mechaharness.eval_trial import Trial, task_trials


class DiscriminativeValueReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    all_success_tie: bool = False
    all_failure_tie: bool = False
    evaluator_tie: bool = False
    secondary_only_distinction: bool = False
    task_trial_count: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


def discriminative_report(
    trials: Sequence[Trial],
    *,
    secondary_metrics: Sequence[float] | None = None,
) -> DiscriminativeValueReport:
    scored = task_trials(list(trials))
    if not scored:
        return DiscriminativeValueReport(task_trial_count=0)
    successes = [t.success for t in scored]
    all_success = all(successes)
    all_failure = not any(successes)
    # Evaluator tie: every trial has identical claim status multiset.
    claim_sigs = []
    for trial in scored:
        sig = tuple(sorted((c.id, c.status) for c in trial.claims))
        claim_sigs.append(sig)
    evaluator_tie = len(set(claim_sigs)) <= 1 and bool(claim_sigs)
    secondary = list(secondary_metrics or ())
    secondary_only = False
    if (all_success or all_failure or evaluator_tie) and secondary:
        secondary_only = len(set(secondary)) > 1
    return DiscriminativeValueReport(
        all_success_tie=all_success,
        all_failure_tie=all_failure,
        evaluator_tie=evaluator_tie,
        secondary_only_distinction=secondary_only,
        task_trial_count=len(scored),
        detail={"unique_claim_signatures": len(set(claim_sigs))},
    )


def claims_all_equal(claims_a: Sequence[Claim], claims_b: Sequence[Claim]) -> bool:
    return sorted((c.id, c.status) for c in claims_a) == sorted(
        (c.id, c.status) for c in claims_b
    )
