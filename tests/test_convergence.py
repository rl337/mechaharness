"""POL-03 convergence contract tests."""

from __future__ import annotations

from mechaharness.convergence import ConvergenceContract, ConvergenceGuard, fingerprint_payload


def test_stagnation_and_exhaustion() -> None:
    guard = ConvergenceGuard(
        ConvergenceContract(version="v1", max_iterations=10, stagnation_window=2)
    )
    assert guard.tick(fingerprint="a").terminal is None
    assert guard.tick(fingerprint="a").terminal is None
    stopped = guard.tick(fingerprint="a")
    assert stopped.terminal == "no_progress"
    assert stopped.reason == "stagnation"


def test_nested_budget_and_ceiling_not_success() -> None:
    parent = ConvergenceGuard(
        ConvergenceContract(version="v1", max_iterations=4, parent_budget_share=0.5)
    )
    child = parent.child()
    assert child.contract.max_iterations == 2
    for _ in range(3):
        child.tick(fingerprint=str(_))
    assert child.state.terminal == "exhaustion"
    assert child.state.terminal != "success"


def test_fingerprint_ignores_mapping_order() -> None:
    assert fingerprint_payload({"b": 1, "a": 2}) == fingerprint_payload({"a": 2, "b": 1})
