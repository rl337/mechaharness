"""AuthorityGate composes access, envelope, consequence, and verdict (MH-PA-02)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mechaharness.authority_gate import AuthorityGate
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.consequence import ActionConsequence, ConsequencePolicy
from mechaharness.core.access import (
    AccessPolicy,
    FsRead,
    GraphExecute,
    InMemoryAccessControl,
)
from mechaharness.core.events import InMemoryEventLog
from mechaharness.denial_store import InMemoryDenialStore, equivalent_action_digest
from mechaharness.judgement_policy import Verdict

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
SEND = "email.send"


def _verdict(kind: str) -> Verdict:
    return Verdict(kind=kind, reasonCodes=["r"], policyVersion="1")  # type: ignore[arg-type]


def _gate(
    *, grants: list[object] | None = None, denials: InMemoryDenialStore | None = None
) -> AuthorityGate:
    return AuthorityGate(
        access=InMemoryAccessControl(
            InMemoryEventLog(), AccessPolicy(grants=grants or [GraphExecute, FsRead])
        ),
        consequence=ConsequencePolicy(
            actions=[
                ActionConsequence(action=SEND, consequence="high"),
                ActionConsequence(action="fs.read", consequence="low"),
            ]
        ),
        denials=denials,
    )


_CASES = [
    # id, kwargs, outcome, reason_codes
    ("low_consequence_allows", {"action": "fs.read", "required_grants": [FsRead]}, "allow", []),
    ("high_consequence_asks", {"action": SEND}, "ask_human", ["consequence_requires_approval"]),
    ("high_consequence_approved", {"action": SEND, "approved": True}, "allow", []),
    (
        "untrusted_source_denied_even_if_approved",
        {"action": SEND, "approved": True, "source_trust": "untrusted"},
        "deny",
        ["untrusted_source"],
    ),
    (
        "untrusted_low_consequence_ok",
        {"action": "fs.read", "source_trust": "untrusted"},
        "allow",
        [],
    ),
    (
        "access_denied",
        {"action": "fs.read", "required_grants": ["core:net.http"]},
        "deny",
        ["access_denied"],
    ),
    ("verdict_deny", {"action": "fs.read", "verdict": _verdict("DENY")}, "deny", ["verdict_deny"]),
    (
        "verdict_ask",
        {"action": "fs.read", "verdict": _verdict("ASK_HUMAN")},
        "ask_human",
        ["verdict_ask_human"],
    ),
    (
        "verdict_abstain_asks",
        {"action": "fs.read", "verdict": _verdict("ABSTAIN")},
        "ask_human",
        ["verdict_abstain"],
    ),
    (
        "verdict_ask_approved",
        {"action": "fs.read", "verdict": _verdict("ASK_HUMAN"), "approved": True},
        "allow",
        [],
    ),
    ("verdict_allow", {"action": "fs.read", "verdict": _verdict("ALLOW")}, "allow", []),
    (
        "envelope_missing_grant",
        {
            "action": "fs.read",
            "required_grants": [FsRead],
            "envelope": CapabilityEnvelope(grants=["core:graph.execute"]),
        },
        "deny",
        ["envelope_grant_missing:core:fs.read"],
    ),
    (
        "envelope_expired",
        {"action": "fs.read", "envelope": CapabilityEnvelope(expires_at="2026-10-18T11:00:00Z")},
        "deny",
        ["envelope_expired"],
    ),
    (
        "envelope_tool_missing",
        {
            "action": "fs.read",
            "tool_name": "Edit",
            "envelope": CapabilityEnvelope(tool_names=["Read"]),
        },
        "deny",
        ["envelope_tool_missing"],
    ),
]


@pytest.mark.parametrize(
    ("case_id", "kwargs", "outcome", "codes"), _CASES, ids=[c[0] for c in _CASES]
)
def test_authority_gate_matrix(case_id: str, kwargs: dict, outcome: str, codes: list[str]) -> None:
    del case_id
    decision = _gate().evaluate(now=NOW, **kwargs)
    assert (decision.outcome, decision.reason_codes) == (outcome, codes)


def test_verdict_deny_is_remembered_and_blocks_equivalent_retry() -> None:
    denials = InMemoryDenialStore()
    gate = _gate(denials=denials)
    digest = equivalent_action_digest(SEND, "bob@x.io")
    first = gate.evaluate(
        action=SEND, verdict=_verdict("DENY"), action_digest=digest, tool_name="smtp"
    )
    assert first.reason_codes == ["verdict_deny"]
    # Retry through another tool with approval and an ALLOW verdict is still refused.
    retry = gate.evaluate(
        action=SEND,
        verdict=_verdict("ALLOW"),
        approved=True,
        action_digest=digest,
        tool_name="graph.send",
    )
    assert (retry.outcome, retry.reason_codes) == ("deny", ["prior_denial"])
    denials.lift(digest)
    assert gate.evaluate(action=SEND, approved=True, action_digest=digest).outcome == "allow"


def test_gate_without_collaborators_allows_everything() -> None:
    assert AuthorityGate().evaluate(action="anything").outcome == "allow"
