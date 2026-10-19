"""Reusable handoff records preserving why, not only what.

WalkingLabs L05 asks to preserve rationale across resets
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-05-why-long-running-tasks-lose-continuity/).
Hosts own storage; MechaHarness owns the schema::

    >>> from mechaharness.handoff_record import HandoffRecord
    >>> rec = HandoffRecord(
    ...     completed=["linked environment"],
    ...     pending=["verify lighthouse"],
    ...     decisions=["chose repair over rewrite"],
    ...     rationale="repair cheaper given existing graph",
    ...     rejected_alternatives=["full rewrite"],
    ...     risks=["flake in e2e"],
    ...     next_action="run verify node",
    ... )
    >>> rec.next_action
    'run verify node'
    >>> rec = HandoffRecord(
    ...     goals=["ship the report"],
    ...     exclusions=["do not email the customer"],
    ...     verdict={"kind": "ASK_HUMAN", "policyVersion": "1"},
    ... )
    >>> rec.exclusions, rec.verdict["kind"]
    (['do not email the customer'], 'ASK_HUMAN')
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HandoffRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1"
    goals: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    completed: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    verification_state: str | None = None
    decisions: list[str] = Field(default_factory=list)
    rationale: str = ""
    rejected_alternatives: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_action: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    # Expected or observed verdict schema (e.g. a ``Verdict`` dump); opaque to the core.
    verdict: dict[str, Any] | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
