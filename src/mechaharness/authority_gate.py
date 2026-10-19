"""One authority gate composing access, envelope, consequence, and verdict (MH-PA-02).

Hard rules for consequential actions live outside model text. The gate asks,
in fail-closed order: was this action already denied; does the capability
envelope still cover it; does access control hold the grants; is the source
trusted for a high-consequence action; did the judgement verdict allow it; and
does the consequence class demand explicit approval::

    >>> from mechaharness.authority_gate import AuthorityGate
    >>> from mechaharness.consequence import ActionConsequence, ConsequencePolicy
    >>> gate = AuthorityGate(consequence=ConsequencePolicy(actions=[
    ...     ActionConsequence(action="email.send", consequence="high"),
    ... ]))
    >>> gate.evaluate(action="email.send").outcome
    'ask_human'
    >>> gate.evaluate(action="email.send", approved=True).outcome
    'allow'
    >>> gate.evaluate(
    ...     action="email.send", approved=True, source_trust="untrusted",
    ... ).reason_codes
    ['untrusted_source']
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.consequence import ConsequencePolicy
from mechaharness.core.access import AccessControl
from mechaharness.denial_store import DenialStore
from mechaharness.judgement_policy import Verdict

AuthorityOutcome = Literal["allow", "deny", "ask_human"]
SourceTrust = Literal["trusted", "untrusted"]


class AuthorityDecision(BaseModel):
    """Gate verdict with machine-readable reasons."""

    model_config = ConfigDict(extra="allow")

    outcome: AuthorityOutcome
    reason_codes: list[str] = Field(default_factory=list)


class AuthorityGate:
    """Compose existing authority axes; every collaborator is optional."""

    def __init__(
        self,
        *,
        access: AccessControl | None = None,
        consequence: ConsequencePolicy | None = None,
        denials: DenialStore | None = None,
    ) -> None:
        self.access = access
        self.consequence = consequence
        self.denials = denials

    def evaluate(
        self,
        *,
        action: str,
        required_grants: Sequence[object] = (),
        envelope: CapabilityEnvelope | None = None,
        verdict: Verdict | None = None,
        source_trust: SourceTrust = "trusted",
        approved: bool = False,
        action_digest: str | None = None,
        tool_name: str = "",
        agent_id: str = "",
        run_id: str = "",
        now: datetime | None = None,
    ) -> AuthorityDecision:
        def deny(code: str) -> AuthorityDecision:
            return AuthorityDecision(outcome="deny", reason_codes=[code])

        if self.denials is not None and action_digest is not None:
            if self.denials.lookup(action_digest) is not None:
                return deny("prior_denial")
        if envelope is not None:
            issue = envelope.authority_issue(
                required_grants=required_grants, tool_name=tool_name, now=now
            )
            if issue is not None:
                return deny(issue)
        if self.access is not None and not self.access.allows(
            required_grants, tool_name=tool_name or action, agent_id=agent_id, run_id=run_id
        ):
            return deny("access_denied")

        strong = (
            self.consequence is not None
            and self.consequence.requires_stronger_controls(action)
        )
        if strong and source_trust == "untrusted":
            return deny("untrusted_source")
        if verdict is not None and verdict.kind == "DENY":
            if self.denials is not None and action_digest is not None:
                self.denials.record(
                    action_digest,
                    reason=",".join(verdict.reason_codes) or "verdict_deny",
                    tool_name=tool_name or None,
                    run_id=run_id or None,
                )
            return deny("verdict_deny")
        if verdict is not None and verdict.kind in {"ASK_HUMAN", "ABSTAIN"} and not approved:
            return AuthorityDecision(
                outcome="ask_human", reason_codes=[f"verdict_{verdict.kind.lower()}"]
            )
        if strong and not approved:
            return AuthorityDecision(
                outcome="ask_human", reason_codes=["consequence_requires_approval"]
            )
        return AuthorityDecision(outcome="allow")
