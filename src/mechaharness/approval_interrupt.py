"""Durable human-approval interrupts with suspend/resume.

WalkingLabs P08 and L14 call for human approval as a durable graph interrupt,
not a soft prompt suggestion
(https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/,
https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/).

MechaHarness models the interrupt payload and resume transition::

    >>> from mechaharness.approval_interrupt import (
    ...     ApprovalInterrupt, suspend_for_approval, resume_approval,
    ... )
    >>> pending = suspend_for_approval(
    ...     reason="Deploy to production",
    ...     consequence_summary="irreversible release",
    ...     allowed_decisions=["approve", "reject"],
    ...     evidence_refs=["verify:ok"],
    ...     suspended_checkpoint_ref="ckpt:42",
    ...     timeout_ms=3_600_000,
    ... )
    >>> pending.status
    'pending'
    >>> done = resume_approval(pending, decision="approve", actor="ops@acme")
    >>> done.status
    'approved'
    >>> done.actor_provenance
    'ops@acme'
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

ApprovalStatus = Literal["pending", "approved", "rejected", "timed_out"]
TimeoutPolicy = Literal["reject", "escalate", "keep_pending"]


class ApprovalInterrupt(BaseModel):
    """Durable approval request that suspends graph progress until resumed."""

    model_config = ConfigDict(extra="allow")

    interrupt_id: str = Field(default_factory=lambda: str(uuid4()))
    version: str = "1"
    status: ApprovalStatus = "pending"
    reason: str
    consequence_summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    allowed_decisions: list[str] = Field(default_factory=lambda: ["approve", "reject"])
    request_payload: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = None
    timeout_policy: TimeoutPolicy = "reject"
    suspended_checkpoint_ref: str | None = None
    actor_provenance: str | None = None
    decision: str | None = None
    resume_transition: str | None = None


def suspend_for_approval(
    *,
    reason: str,
    consequence_summary: str = "",
    allowed_decisions: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    request_payload: dict[str, Any] | None = None,
    timeout_ms: int | None = None,
    timeout_policy: TimeoutPolicy = "reject",
    suspended_checkpoint_ref: str | None = None,
    resume_transition: str | None = None,
) -> ApprovalInterrupt:
    return ApprovalInterrupt(
        reason=reason,
        consequence_summary=consequence_summary,
        allowed_decisions=list(allowed_decisions or ["approve", "reject"]),
        evidence_refs=list(evidence_refs or ()),
        request_payload=dict(request_payload or {}),
        timeout_ms=timeout_ms,
        timeout_policy=timeout_policy,
        suspended_checkpoint_ref=suspended_checkpoint_ref,
        resume_transition=resume_transition,
        status="pending",
    )


def resume_approval(
    interrupt: ApprovalInterrupt,
    *,
    decision: str,
    actor: str,
) -> ApprovalInterrupt:
    if interrupt.status != "pending":
        raise ValueError(f"interrupt {interrupt.interrupt_id} is not pending")
    if decision not in interrupt.allowed_decisions:
        raise ValueError(f"decision {decision!r} not in {interrupt.allowed_decisions}")
    status: ApprovalStatus = "approved" if decision == "approve" else "rejected"
    if decision not in ("approve", "reject"):
        status = "approved" if decision.startswith("approve") else "rejected"
    return interrupt.model_copy(
        update={
            "status": status,
            "decision": decision,
            "actor_provenance": actor,
        }
    )


def apply_timeout(interrupt: ApprovalInterrupt) -> ApprovalInterrupt:
    if interrupt.status != "pending":
        return interrupt
    if interrupt.timeout_policy == "keep_pending":
        return interrupt
    status: ApprovalStatus = "timed_out"
    decision = "timeout"
    if interrupt.timeout_policy == "reject":
        status = "rejected"
        decision = "timeout_reject"
    return interrupt.model_copy(update={"status": status, "decision": decision})
