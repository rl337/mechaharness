"""Consequence / risk classes for risk-scaled autonomy (req 15).

Soft guidance never substitutes for grants. Consequence classes scale
verification, envelope narrowing, and approval prompts — grants remain the
hard gate.

In *Governing agent autonomy with Auto-review*, the Cursor developer blog
suggests treating autonomy as a dial — low-stakes actions proceed, crossing
trust boundaries slows the agent — and tracking approval frequency because
prompt fatigue degrades review
(https://cursor.com/blog/agent-autonomy-auto-review)::

    >>> from mechaharness.consequence import ActionConsequence, ConsequencePolicy
    >>> policy = ConsequencePolicy(actions=[
    ...     ActionConsequence(action="Bash(ls)", consequence="low"),
    ...     ActionConsequence(
    ...         action="Bash(curl prod)",
    ...         consequence="high",
    ...         trust_boundary="production_network",
    ...         requires_approval=True,
    ...     ),
    ... ])
    >>> policy.for_action("Bash(ls)").consequence
    'low'
    >>> policy.requires_stronger_controls("Bash(curl prod)")
    True
    >>> policy.record_approval_prompt(); policy.record_approval_decision()
    >>> policy.approval_frequency()
    1.0
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConsequenceClass = Literal["low", "medium", "high", "critical"]


class ActionConsequence(BaseModel):
    """Declared consequence for an action or grant-gated operation."""

    model_config = ConfigDict(extra="allow")

    action: str
    consequence: ConsequenceClass = "medium"
    trust_boundary: str | None = None
    requires_approval: bool = False
    force_exhaustive_verification: bool = False
    notes: str = ""


class ConsequencePolicy(BaseModel):
    """Map actions to consequence; expose approval-frequency metrics hooks."""

    model_config = ConfigDict(extra="allow")

    actions: list[ActionConsequence] = Field(default_factory=list)
    approval_prompts: int = 0
    approval_decisions: int = 0

    def for_action(self, action: str) -> ActionConsequence:
        for item in self.actions:
            if item.action == action:
                return item
        return ActionConsequence(action=action, consequence="medium")

    def record_approval_prompt(self) -> None:
        self.approval_prompts += 1

    def record_approval_decision(self) -> None:
        self.approval_decisions += 1

    def approval_frequency(self) -> float | None:
        if self.approval_prompts <= 0:
            return None
        return self.approval_decisions / self.approval_prompts

    def requires_stronger_controls(self, action: str) -> bool:
        item = self.for_action(action)
        return item.consequence in {"high", "critical"} or item.requires_approval
