from mechaharness.eval_evidence import Claim
from mechaharness.objective_policy import (
    ObjectivePolicy,
    aggregate_objective,
    compare_lexicographic,
)


def test_gate_failure_not_silent_pass() -> None:
    policy = ObjectivePolicy(
        policy_id="p",
        component_signals=["correct", "tokens"],
        formula="gated_primary",
        gates=["correct"],
    )
    result = aggregate_objective(
        policy,
        [Claim(id="correct", statement="c", status="fail")],
    )
    assert not result.gates_satisfied
    assert result.scalar == 0.0


def test_unknown_claim_unscorable() -> None:
    policy = ObjectivePolicy(
        policy_id="p",
        component_signals=["a"],
        formula="all_pass",
    )
    result = aggregate_objective(
        policy,
        [Claim(id="a", statement="a", status="unknown")],
    )
    assert result.unscorable


def test_lexicographic_compare() -> None:
    policy = ObjectivePolicy(
        policy_id="p",
        lexicographic=["correct", "efficiency"],
    )
    assert (
        compare_lexicographic(
            policy,
            {"correct": 1.0, "efficiency": 0.5},
            {"correct": 1.0, "efficiency": 0.9},
        )
        == "control"
    )
