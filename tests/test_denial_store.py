"""DenialStore equivalence keys and in-memory reference (MH-DOTS-05)."""

from __future__ import annotations

from mechaharness.denial_store import (
    DenialStore,
    InMemoryDenialStore,
    equivalent_action_digest,
)


def test_digest_ignores_provider_but_not_target_or_class() -> None:
    a = equivalent_action_digest("email.send", "bob@x.io")
    assert a == equivalent_action_digest("email.send", "bob@x.io")
    assert a != equivalent_action_digest("email.send", "amy@x.io")
    assert a != equivalent_action_digest("sms.send", "bob@x.io")
    assert a != equivalent_action_digest("email.send", "bob@x.io", cc="amy")


def test_denial_survives_alias_tool_and_lift_requires_explicit_call() -> None:
    store: DenialStore = InMemoryDenialStore()
    digest = equivalent_action_digest("email.send", "bob@x.io")
    first = store.record(digest, reason="user_denied", tool_name="smtp.send", run_id="r1")
    # Second provider records the same intent: first denial wins, nothing duplicates.
    assert store.record(digest, reason="retry", tool_name="graph.send") is first
    found = store.lookup(equivalent_action_digest("email.send", "bob@x.io"))
    assert found is not None and found.tool_name == "smtp.send" and found.reason == "user_denied"
    assert store.lift(digest) is True
    assert store.lift(digest) is False
    assert store.lookup(digest) is None
