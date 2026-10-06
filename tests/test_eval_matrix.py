from mechaharness.eval_matrix import EvalMatrix
from mechaharness.eval_trial import Trial


def test_matrix_retains_cells() -> None:
    matrix = EvalMatrix()
    matrix.add_trial(
        Trial(trial_id="1", success=True),
        model="m1",
        harness_fingerprint="fp:a",
        task_family="math",
    )
    matrix.add_trial(
        Trial(trial_id="2", success=False),
        model="m1",
        harness_fingerprint="fp:b",
        task_family="math",
    )
    agg = matrix.aggregate()
    assert agg["cell_count"] == 2
    assert len(agg["cells"]) == 2
    assert {c["harness_fingerprint"] for c in agg["cells"]} == {"fp:a", "fp:b"}
