from mechaharness.harness_experiment import HarnessExperiment, HarnessExperimentRunner
from mechaharness.objective_policy import ObjectivePolicy


def test_efficiency_cannot_beat_failed_gate() -> None:
    runner = HarnessExperimentRunner()
    exp = runner.propose(
        HarnessExperiment(
            hypothesis="cheap but wrong",
            intervention="skip_verify",
            failure_mode="incorrect",
        )
    )
    policy = ObjectivePolicy(
        policy_id="lexi",
        gates=["correct"],
        lexicographic=["correct", "efficiency"],
    )
    result = runner.evaluate(
        exp,
        with_intervention=lambda: {"correct": 0.0, "efficiency": 0.9},
        without_intervention=lambda: {"correct": 1.0, "efficiency": 0.5},
        objective_policy=policy,
    )
    assert result.status == "retired"
