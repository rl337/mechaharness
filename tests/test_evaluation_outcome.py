from mechaharness.eval_trial import Trial, pass_at_k, task_trials, trial_cost_rollup
from mechaharness.evaluation_outcome import (
    EvaluationOutcome,
    is_task_scored,
    outcome_from_failure,
)


def test_infra_failure_not_task_scored() -> None:
    dead = outcome_from_failure("environment:sandbox_dead")
    assert dead.kind == "execution_failure"
    assert not is_task_scored(dead)


def test_pass_at_k_excludes_execution_failure() -> None:
    trials = [
        Trial(trial_id="1", success=True),
        Trial(trial_id="2", success=True),
        Trial(
            trial_id="3",
            success=False,
            outcome=EvaluationOutcome(kind="execution_failure"),
        ),
    ]
    assert len(task_trials(trials)) == 2
    assert pass_at_k(trials, k=1) == 1.0
    rollup = trial_cost_rollup(trials)
    assert rollup["task_trials"] == 2.0
    assert rollup["non_task_trials"] == 1.0
