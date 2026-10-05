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
"""

from __future__ import annotations

from typing import Any, Literal

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
