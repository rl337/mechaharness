from mechaharness.eval_trial import Trial, pass_at_k, pass_caret_k, trial_cost_rollup


def test_pass_metrics() -> None:
    trials = [
        Trial(trial_id="1", success=True, cost_usd=0.1, latency_ms=10),
        Trial(trial_id="2", success=True, cost_usd=0.1, latency_ms=20),
        Trial(trial_id="3", success=False, cost_usd=0.2, latency_ms=30),
    ]
    assert pass_at_k(trials, k=1) > 0
    assert 0 <= pass_caret_k(trials, k=2) <= 1
    rollup = trial_cost_rollup(trials)
    assert rollup["total_cost_usd"] == 0.4
