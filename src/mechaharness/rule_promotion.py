"""Evidence-bearing promotion from review feedback to enforceable rules.

WalkingLabs L10/L12 describe promoting repeated review feedback into process
changes with provenance and rollback
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-10-why-end-to-end-testing-changes-results/,
https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/).

::

    >>> from mechaharness.rule_promotion import PromotionRecord, promote_soft_to_hard
    >>> rec = PromotionRecord(
    ...     observed_pattern="missing changelog",
    ...     hypothesis="require changelog check",
    ...     experiment_ref="exp:1",
    ...     soft_instruction_ref="skill:changelog",
    ...     source_permalink="https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-10-why-end-to-end-testing-changes-results/",
    ... )
    >>> hard = promote_soft_to_hard(rec, hard_invariant_ref="check:changelog")
    >>> hard.stage
    'hard'

Specification debt (MH-PA-07)
-----------------------------

A human correction is evidence that the specification (rules, tests, recipes)
was incomplete. The ledger records the correction, the failing scenarios it
came from, and a link to the :class:`~mechaharness.rule_promotion.PromotionRecord`
that may harden it. MechaHarness owns only this schema: the host generates the
regression test, and ``review_required`` stays true until a human accepts it::

    >>> from mechaharness.rule_promotion import (
    ...     PromotionRecord, SpecificationDebtLedger, capture_correction,
    ... )
    >>> promotion = PromotionRecord(
    ...     record_id="promo:1", observed_pattern="sent to wrong thread",
    ... )
    >>> ledger = SpecificationDebtLedger()
    >>> item = ledger.add(capture_correction(
    ...     "Reply on the original thread, never a new one.",
    ...     failing_scenarios=["scenario:reply-thread"],
    ...     promotion=promotion,
    ... ))
    >>> item.review_required, item.status, item.promotion_record_id
    (True, 'open', 'promo:1')
    >>> [i.id for i in ledger.pending_review()] == [item.id]
    True
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

PromotionStage = Literal[
    "observed",
    "hypothesis",
    "experiment",
    "soft",
    "hard",
    "rolled_back",
]


class PromotionRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1"
    # Optional stable id so ledgers (for example specification debt) can link here.
    record_id: str | None = None
    stage: PromotionStage = "observed"
    observed_pattern: str
    hypothesis: str = ""
    experiment_ref: str | None = None
    soft_instruction_ref: str | None = None
    hard_invariant_ref: str | None = None
    source_permalink: str | None = None
    rollback_evidence_ref: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


def promote_soft_to_hard(
    record: PromotionRecord, *, hard_invariant_ref: str
) -> PromotionRecord:
    return record.model_copy(
        update={"stage": "hard", "hard_invariant_ref": hard_invariant_ref}
    )


def rollback_promotion(
    record: PromotionRecord, *, rollback_evidence_ref: str
) -> PromotionRecord:
    return record.model_copy(
        update={
            "stage": "rolled_back",
            "rollback_evidence_ref": rollback_evidence_ref,
        }
    )


SpecificationDebtStatus = Literal["open", "test_linked", "closed"]


class SpecificationDebtRecord(BaseModel):
    """One correction awaiting a reviewed, host-generated regression test."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    id: str = Field(default_factory=lambda: f"specdebt:{uuid4().hex[:12]}")
    correction: str
    failing_scenario_refs: list[str] = Field(default_factory=list)
    promotion_record_id: str | None = None
    review_required: bool = True
    status: SpecificationDebtStatus = "open"
    generated_test_ref: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    def link_test(self, test_ref: str) -> SpecificationDebtRecord:
        """Record the host-generated regression test (still pending review)."""
        return self.model_copy(
            update={"status": "test_linked", "generated_test_ref": test_ref}
        )

    def approve(self) -> SpecificationDebtRecord:
        """Human review accepted the correction and its test."""
        return self.model_copy(update={"review_required": False, "status": "closed"})


def capture_correction(
    correction: str,
    *,
    failing_scenarios: Sequence[str] = (),
    promotion: PromotionRecord | None = None,
    promotion_record_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> SpecificationDebtRecord:
    """Turn a human correction into a reviewable debt record (no test generation)."""
    if not correction.strip():
        raise ValueError("a correction needs non-empty text")
    linked = promotion_record_id or (promotion.record_id if promotion else None)
    return SpecificationDebtRecord(
        correction=correction,
        failing_scenario_refs=list(failing_scenarios),
        promotion_record_id=linked,
        detail=dict(detail or {}),
    )


class SpecificationDebtLedger:
    """In-memory reference ledger; hosts persist records themselves."""

    def __init__(self) -> None:
        self._records: dict[str, SpecificationDebtRecord] = {}

    def add(self, record: SpecificationDebtRecord) -> SpecificationDebtRecord:
        self._records[record.id] = record
        return record

    def get(self, record_id: str) -> SpecificationDebtRecord:
        return self._records[record_id]

    def update(self, record: SpecificationDebtRecord) -> SpecificationDebtRecord:
        if record.id not in self._records:
            raise KeyError(f"unknown specification debt record {record.id!r}")
        self._records[record.id] = record
        return record

    def records(self) -> list[SpecificationDebtRecord]:
        return list(self._records.values())

    def pending_review(self) -> list[SpecificationDebtRecord]:
        return [r for r in self._records.values() if r.review_required]

    def for_promotion(self, promotion_record_id: str) -> list[SpecificationDebtRecord]:
        return [
            r
            for r in self._records.values()
            if r.promotion_record_id == promotion_record_id
        ]
