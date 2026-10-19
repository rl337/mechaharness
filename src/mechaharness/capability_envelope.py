"""Capability envelopes for graph and delegated execution.

An envelope is the hard boundary for a run or child: tools, grants, context
providers, model class, budgets, escalation, and output contract. Children
MUST receive an explicit envelope; they do not inherit the parent implicitly.

In *How and when to use subagents in Claude Code*, the Claude developer blog
suggests children receive isolated context and restricted tools rather than
inheriting the parent session
(https://claude.com/blog/subagents-in-claude-code).
In *Implementing a secure sandbox for local agents*, the Cursor developer
blog suggests structural capability boundaries instead of prompt-only hope
(https://cursor.com/blog/agent-sandboxing)::

    >>> from mechaharness.capability_envelope import CapabilityEnvelope
    >>> from mechaharness.core.access import FsRead, FsWrite, GraphExecute
    >>> parent = CapabilityEnvelope.from_grants(
    ...     [GraphExecute, FsRead, FsWrite],
    ...     tool_names=["Read", "Edit"],
    ...     model_class="reason-fast",
    ...     resource_budget={"max_tokens": 50_000},
    ... )
    >>> explorer = parent.narrow(
    ...     grants=[GraphExecute, FsRead],
    ...     tool_names=["Read"],
    ...     context_provider_ids=["repo.index"],
    ...     parent_state_version="main@abc",
    ... )
    >>> explorer.tool_names, explorer.allows_grant(FsWrite)
    (['Read'], False)
    >>> parent.narrow(grants=[GraphExecute, FsRead, "core:net.http"])
    Traceback (most recent call last):
        ...
    ValueError: child envelope widens grants: core:net.http

An envelope doubles as a capability-scoped execution token: it may carry the
acting ``principal``, an ``expires_at`` bound, the ``trust_origin`` of the
request, and the ``authorization_epoch`` that checkpoints compare on resume.
Children can only attenuate those fields (OpenAI Dots agent safety,
MH-DOTS-01)::

    >>> token = CapabilityEnvelope.from_grants(
    ...     [GraphExecute, FsRead],
    ...     principal="user:fangore",
    ...     expires_at="2026-10-18T12:00:00Z",
    ...     trust_origin="host:console",
    ...     authorization_epoch=3,
    ... )
    >>> child = token.narrow(expires_at="2026-10-18T11:00:00Z")
    >>> child.principal, child.authorization_epoch
    ('user:fangore', 3)
    >>> token.narrow(authorization_epoch=4)
    Traceback (most recent call last):
        ...
    ValueError: child envelope widens authorization_epoch: 4 > 3
    >>> token.narrow(expires_at="2026-10-18T13:00:00Z")
    Traceback (most recent call last):
        ...
    ValueError: child envelope widens expires_at: 2026-10-18T13:00:00Z > 2026-10-18T12:00:00Z
    >>> token.narrow(trust_origin="host:webhook")
    Traceback (most recent call last):
        ...
    ValueError: child envelope changes trust_origin: 'host:webhook' != 'host:console'
    >>> from datetime import datetime, timezone
    >>> token.is_expired(now=datetime(2026, 10, 18, 13, tzinfo=timezone.utc))
    True
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.access import grant_key
from mechaharness.iso_timestamp import parse_iso_timestamp


def _expiry_widens(parent: str, child: str) -> bool:
    """True when ``child`` outlives ``parent`` (opaque values must match)."""
    if parent == child:
        return False
    parent_dt = parse_iso_timestamp(parent)
    child_dt = parse_iso_timestamp(child)
    if parent_dt is not None and child_dt is not None:
        return child_dt > parent_dt
    # Opaque or mixed formats cannot be ordered: fail closed.
    return True


class CapabilityEnvelope(BaseModel):
    """Declared capability boundary for one execution scope."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    tool_names: list[str] = Field(default_factory=list)
    grants: list[str] = Field(default_factory=list)
    context_provider_ids: list[str] = Field(default_factory=list)
    model_class: str | None = None
    resource_budget: dict[str, Any] = Field(default_factory=dict)
    stop_contract_ref: str | None = None
    outcome_contract_ref: str | None = None
    escalation_policy: str = "reject"
    output_contract: dict[str, Any] = Field(default_factory=dict)
    parent_state_version: str | None = None
    principal: str | None = None
    expires_at: str | None = None
    trust_origin: str | None = None
    authorization_epoch: int = 0

    @classmethod
    def from_grants(
        cls,
        grants: Sequence[object],
        *,
        tool_names: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> CapabilityEnvelope:
        return cls(
            grants=[grant_key(item) for item in grants],
            tool_names=list(tool_names or []),
            **kwargs,
        )

    def authority_issue(
        self,
        *,
        required_grants: Sequence[object] = (),
        tool_name: str = "",
        live_authorization_epoch: int | None = None,
        now: datetime | None = None,
    ) -> str | None:
        """First reason this envelope no longer covers an action, else ``None``.

        Shared by ``AuthorityGate`` and ``revalidate_before_effect`` so both emit
        the same reason codes, checked in fail-closed order: expiry, advanced
        authorization epoch (only when ``live_authorization_epoch`` is given),
        tool not in a non-empty ``tool_names``, then a missing grant.

            >>> env = CapabilityEnvelope(grants=["core:fs.read"], authorization_epoch=2)
            >>> env.authority_issue(required_grants=["core:fs.read"])
            >>> env.authority_issue(live_authorization_epoch=3)
            'authorization_epoch_advanced:2!=3'
            >>> env.authority_issue(required_grants=["core:fs.write"])
            'envelope_grant_missing:core:fs.write'
        """
        if self.is_expired(now=now):
            return "envelope_expired"
        if (
            live_authorization_epoch is not None
            and live_authorization_epoch != self.authorization_epoch
        ):
            return (
                "authorization_epoch_advanced:"
                f"{self.authorization_epoch}!={live_authorization_epoch}"
            )
        if tool_name and self.tool_names and tool_name not in self.tool_names:
            return "envelope_tool_missing"
        for required in required_grants:
            if not self.allows_grant(required):
                return f"envelope_grant_missing:{grant_key(required)}"
        return None

    def narrow(
        self,
        *,
        grants: Sequence[object] | None = None,
        tool_names: Sequence[str] | None = None,
        context_provider_ids: Sequence[str] | None = None,
        resource_budget: Mapping[str, Any] | None = None,
        parent_state_version: str | None = None,
        principal: str | None = None,
        expires_at: str | None = None,
        trust_origin: str | None = None,
        authorization_epoch: int | None = None,
        **kwargs: Any,
    ) -> CapabilityEnvelope:
        """Return a child envelope that does not widen parent authority.

        Besides grants and tools, a child may not raise ``authorization_epoch``,
        change a set ``principal`` or ``trust_origin``, or outlive the parent's
        ``expires_at``. Omitted token fields are inherited.
        """
        parent_grants = set(self.grants)
        child_grants = (
            [grant_key(item) for item in grants]
            if grants is not None
            else list(self.grants)
        )
        if not set(child_grants).issubset(parent_grants) and parent_grants:
            missing = sorted(set(child_grants) - parent_grants)
            raise ValueError(f"child envelope widens grants: {', '.join(missing)}")
        parent_tools = set(self.tool_names)
        child_tools = list(tool_names) if tool_names is not None else list(self.tool_names)
        if parent_tools and not set(child_tools).issubset(parent_tools):
            missing = sorted(set(child_tools) - parent_tools)
            raise ValueError(f"child envelope widens tools: {', '.join(missing)}")
        if (
            authorization_epoch is not None
            and authorization_epoch > self.authorization_epoch
        ):
            raise ValueError(
                "child envelope widens authorization_epoch: "
                f"{authorization_epoch} > {self.authorization_epoch}"
            )
        if (
            principal is not None
            and self.principal is not None
            and principal != self.principal
        ):
            raise ValueError(
                f"child envelope changes principal: {principal!r} != {self.principal!r}"
            )
        if (
            trust_origin is not None
            and self.trust_origin is not None
            and trust_origin != self.trust_origin
        ):
            raise ValueError(
                "child envelope changes trust_origin: "
                f"{trust_origin!r} != {self.trust_origin!r}"
            )
        if (
            expires_at is not None
            and self.expires_at is not None
            and _expiry_widens(self.expires_at, expires_at)
        ):
            raise ValueError(
                f"child envelope widens expires_at: {expires_at} > {self.expires_at}"
            )
        updates: dict[str, Any] = {
            "grants": child_grants,
            "tool_names": child_tools,
            "context_provider_ids": (
                list(context_provider_ids)
                if context_provider_ids is not None
                else list(self.context_provider_ids)
            ),
            "resource_budget": (
                dict(resource_budget)
                if resource_budget is not None
                else dict(self.resource_budget)
            ),
            "parent_state_version": parent_state_version or self.parent_state_version,
            "principal": principal if principal is not None else self.principal,
            "expires_at": expires_at if expires_at is not None else self.expires_at,
            "trust_origin": (
                trust_origin if trust_origin is not None else self.trust_origin
            ),
            "authorization_epoch": (
                authorization_epoch
                if authorization_epoch is not None
                else self.authorization_epoch
            ),
        }
        updates.update(kwargs)
        return self.model_copy(update=updates)

    def allows_grant(self, required: object) -> bool:
        if not self.grants:
            return True
        return grant_key(required) in self.grants

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """True when ``expires_at`` parses as ISO and is not after ``now``.

        Opaque ``expires_at`` values are never reported expired here; hosts
        that use opaque tokens own their own clock.
        """
        expiry = parse_iso_timestamp(self.expires_at)
        if expiry is None:
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current >= expiry
