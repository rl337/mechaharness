"""CrossTaskIsolationGuard blocks bleed across intervening tasks (MH-DOTS-07)."""

from __future__ import annotations

import pytest

from mechaharness.handoff_record import HandoffRecord
from mechaharness.isolation.cross_task_isolation import CrossTaskIsolationGuard, IsolationViolation
from mechaharness.isolation.isolation_contract import IsolationContract

CONTRACT = IsolationContract(input_context_refs=["goal"])


@pytest.mark.parametrize("intervening", [0, 1, 5, 10])
def test_task_local_ref_does_not_bleed_across_intervening_tasks(intervening: int) -> None:
    guard = CrossTaskIsolationGuard()
    guard.open_task("origin", CONTRACT)
    guard.publish("origin", "approval:send-42")
    for i in range(intervening):
        guard.open_task(f"t{i}", CONTRACT)
        assert guard.can_read(f"t{i}", "goal")
        assert not guard.can_read(f"t{i}", "approval:send-42")
        guard.close_task(f"t{i}")
    guard.open_task("later", CONTRACT)
    assert not guard.can_read("later", "approval:send-42")
    assert guard.can_read("origin", "approval:send-42")


def test_explicit_handoff_is_the_only_sharing_path() -> None:
    guard = CrossTaskIsolationGuard()
    for task in ("a", "b", "c"):
        guard.open_task(task, CONTRACT)
    guard.publish("a", "memo:1")
    guard.publish("a", "memo:2")
    guard.share("a", "b", HandoffRecord(evidence_refs=["memo:1"]))
    assert guard.can_read("b", "memo:1")
    assert not guard.can_read("b", "memo:2")
    assert not guard.can_read("c", "memo:1")


def test_cannot_hand_off_what_the_source_cannot_read() -> None:
    guard = CrossTaskIsolationGuard()
    guard.open_task("a", CONTRACT)
    guard.open_task("b", CONTRACT)
    with pytest.raises(IsolationViolation, match="unreadable"):
        guard.share("a", "b", HandoffRecord(evidence_refs=["memo:ghost"]))


def test_ref_ownership_and_open_state_are_enforced() -> None:
    guard = CrossTaskIsolationGuard()
    guard.open_task("a", CONTRACT)
    guard.open_task("b", CONTRACT)
    guard.publish("a", "memo:1")
    with pytest.raises(IsolationViolation, match="owned by"):
        guard.publish("b", "memo:1")
    with pytest.raises(IsolationViolation, match="not open"):
        guard.publish("zzz", "memo:2")
    with pytest.raises(IsolationViolation, match="cannot read"):
        guard.assert_readable("b", "memo:1")


def test_invalid_contract_is_rejected() -> None:
    with pytest.raises(IsolationViolation, match="budget_share"):
        CrossTaskIsolationGuard().open_task("a", IsolationContract(budget_share=0))
