"""BudgetPolicy / Budget unit checks."""

from __future__ import annotations

import pytest

from mechaharness.budget import Budget, BudgetLevel, BudgetPolicy


def test_unlimited_hard_never_hard() -> None:
    policy = BudgetPolicy.unlimited()
    budget = Budget(policy)
    assert budget.charge(1000) is BudgetLevel.OK
    assert budget.remaining_hard() is None


def test_soft_then_hard_levels() -> None:
    budget = Budget(BudgetPolicy(soft_limit=2, hard_limit=5))
    assert budget.charge(2) is BudgetLevel.SOFT
    assert budget.charge(3) is BudgetLevel.HARD


def test_child_aggregates_to_parent() -> None:
    parent = Budget(BudgetPolicy(soft_limit=10, hard_limit=20))
    child = parent.child(share=0.5)
    child.charge(3, node_id="n", kind="compute")
    assert child.spent == 3
    assert parent.spent == 3
    assert child.policy.hard_limit == 10


def test_soft_above_hard_rejected() -> None:
    with pytest.raises(ValueError, match="soft_limit"):
        BudgetPolicy(soft_limit=5, hard_limit=1)
