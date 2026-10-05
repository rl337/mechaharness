"""Clean-state / exit contracts for post-run handoff readiness.

WalkingLabs L12 treats clean session handoff as part of done
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/).

MechaHarness provides an optional exit contract; repository-specific checks
remain host-supplied::

    >>> from mechaharness.exit_contract import CleanStateContract, evaluate_exit
    >>> contract = CleanStateContract(
    ...     require_checkpoint=True,
    ...     disallow_pending_nodes=True,
    ...     require_handoff_record=True,
    ... )
    >>> report = evaluate_exit(
    ...     contract,
    ...     pending_nodes=[],
    ...     checkpoint_durable=True,
    ...     unresolved_effects=[],
    ...     handoff_record_ref="handoff:1",
    ... )
    >>> report.ok
    True
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CleanStateContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1"
    require_checkpoint: bool = True
    disallow_pending_nodes: bool = True
    disallow_unresolved_effects: bool = True
    require_handoff_record: bool = False
    cleanup_hooks: list[str] = Field(default_factory=list)


class ExitReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool
    issues: list[str] = Field(default_factory=list)
    handoff_record_ref: str | None = None


def evaluate_exit(
    contract: CleanStateContract,
    *,
    pending_nodes: list[str],
    checkpoint_durable: bool,
    unresolved_effects: list[str],
    handoff_record_ref: str | None = None,
) -> ExitReport:
    issues: list[str] = []
    if contract.require_checkpoint and not checkpoint_durable:
        issues.append("checkpoint_not_durable")
    if contract.disallow_pending_nodes and pending_nodes:
        issues.append("pending_nodes")
    if contract.disallow_unresolved_effects and unresolved_effects:
        issues.append("unresolved_effects")
    if contract.require_handoff_record and not handoff_record_ref:
        issues.append("missing_handoff_record")
    return ExitReport(
        ok=not issues,
        issues=issues,
        handoff_record_ref=handoff_record_ref,
    )


# Alias used in inspiration docs
ExitContract = CleanStateContract
