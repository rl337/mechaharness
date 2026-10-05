import pytest

from mechaharness.approval_interrupt import resume_approval, suspend_for_approval


def test_suspend_resume() -> None:
    pending = suspend_for_approval(reason="ship", suspended_checkpoint_ref="c1")
    assert pending.status == "pending"
    done = resume_approval(pending, decision="approve", actor="ops")
    assert done.status == "approved"
    assert done.actor_provenance == "ops"


def test_invalid_decision() -> None:
    pending = suspend_for_approval(reason="x")
    with pytest.raises(ValueError):
        resume_approval(pending, decision="maybe", actor="ops")
