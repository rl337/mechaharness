"""Evaluation outcome taxonomy distinct from binary trial success (MH-MHRL-06).

FineEnvs keeps verifier/infrastructure failures distinct from negative task
reward — a dead sandbox is not evidence the model answered incorrectly
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#rewards).

MechaHarness records open, namespaced outcome kinds so aggregators can exclude
non-task outcomes from task-success denominators::

    >>> from mechaharness.evaluation_outcome import (
    ...     EvaluationOutcome, is_task_scored, outcome_from_failure,
    ... )
    >>> ok = EvaluationOutcome(kind="success")
    >>> dead = outcome_from_failure("environment:sandbox_dead")
    >>> is_task_scored(ok), is_task_scored(dead)
    (True, False)
    >>> dead.kind
    'execution_failure'
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Core vocabulary (hosts may emit other namespaced kinds).
TASK_SCORED_KINDS = frozenset({"success", "task_failure"})
NON_TASK_KINDS = frozenset(
    {
        "execution_failure",
        "invalid_trace",
        "unscorable",
        "cancelled",
        "superseded",
    }
)


class EvaluationOutcome(BaseModel):
    """One evaluation label; ``kind`` is an open string (namespaced OK)."""

    model_config = ConfigDict(extra="allow")

    kind: str
    reason: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)

    @property
    def task_scored(self) -> bool:
        return self.kind in TASK_SCORED_KINDS

    @property
    def success(self) -> bool | None:
        if self.kind == "success":
            return True
        if self.kind == "task_failure":
            return False
        return None


def is_task_scored(outcome: EvaluationOutcome | str | None) -> bool:
    if outcome is None:
        return True  # legacy binary trials without outcome are treated as scored
    kind = outcome.kind if isinstance(outcome, EvaluationOutcome) else outcome
    return kind in TASK_SCORED_KINDS


def outcome_from_failure(code: str, *, evidence_refs: list[str] | None = None) -> EvaluationOutcome:
    """Map coarse failure codes to non-task or task outcomes."""
    lowered = code.lower()
    if any(
        token in lowered
        for token in (
            "sandbox",
            "environment",
            "linkage",
            "timeout",
            "infra",
            "oom",
            "connection",
        )
    ):
        kind = "execution_failure"
    elif any(token in lowered for token in ("trace", "envelope", "integrity", "reconcile")):
        kind = "invalid_trace"
    elif any(token in lowered for token in ("cancel",)):
        kind = "cancelled"
    elif any(token in lowered for token in ("supersede", "preempt")):
        kind = "superseded"
    elif any(token in lowered for token in ("unscorable", "unknown", "held_out_gate")):
        kind = "unscorable"
    else:
        kind = "task_failure"
    return EvaluationOutcome(
        kind=kind,
        reason=code,
        evidence_refs=list(evidence_refs or ()),
    )


def outcome_from_success() -> EvaluationOutcome:
    return EvaluationOutcome(kind="success")
