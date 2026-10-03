"""Capability envelopes for graph and delegated execution.

An envelope is the hard boundary for a run or child: tools, grants, context
providers, model class, budgets, escalation, and output contract. Children
MUST receive an explicit envelope; they do not inherit the parent implicitly.

Mirrors Claude Code subagents (isolated context + restricted tools) and
Cursor sandbox/autonomy posts (structural boundaries, not prompt hope)::

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
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.access import grant_key


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

    def narrow(
        self,
        *,
        grants: Sequence[object] | None = None,
        tool_names: Sequence[str] | None = None,
        context_provider_ids: Sequence[str] | None = None,
        resource_budget: Mapping[str, Any] | None = None,
        parent_state_version: str | None = None,
        **kwargs: Any,
    ) -> CapabilityEnvelope:
        """Return a child envelope that does not widen parent grants/tools."""
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
        }
        updates.update(kwargs)
        return self.model_copy(update=updates)

    def allows_grant(self, required: object) -> bool:
        if not self.grants:
            return True
        return grant_key(required) in self.grants
