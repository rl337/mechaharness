"""Experiment sampling lineage and resume checkpoints (MH-MHRL-13).

FineEnvs observed a resume bug that replayed already-seen tasks and
contaminated the later training distribution
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#why-the-two-harbor-runs-declined).

MechaHarness persists consumed cases, sampler state, assignment, and evidence
digests so resume refuses silent re-consume::

    >>> from mechaharness.experiment_lineage import ExperimentCheckpoint
    >>> ckpt = ExperimentCheckpoint(
    ...     experiment_id="exp-1",
    ...     assignment="treatment",
    ...     checkpoint_id="ckpt-1",
    ... )
    >>> ckpt = ckpt.consume("case-a", evidence_digest="sha:1")
    >>> ckpt.would_duplicate("case-a")
    True
    >>> ckpt.consume("case-a")
    Traceback (most recent call last):
        ...
    ValueError: case already consumed: case-a
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.model_input_manifest import content_digest


class ExperimentCheckpoint(BaseModel):
    """Durable sampling lineage for an evaluation/training experiment shard."""

    model_config = ConfigDict(extra="allow")

    experiment_id: str
    checkpoint_id: str = Field(default_factory=lambda: str(uuid4()))
    assignment: str = "treatment"
    consumed_case_ids: list[str] = Field(default_factory=list)
    sampler_state: dict[str, Any] = Field(default_factory=dict)
    assignment_map: dict[str, str] = Field(default_factory=dict)
    evidence_digests: dict[str, str] = Field(default_factory=dict)
    ordering: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)

    def would_duplicate(self, case_id: str) -> bool:
        return case_id in self.consumed_case_ids

    def has_evidence_digest(self, digest: str) -> bool:
        return digest in self.evidence_digests.values()

    def consume(
        self,
        case_id: str,
        *,
        evidence_digest: str | None = None,
        assignment: str | None = None,
        sampler_state: Mapping[str, Any] | None = None,
    ) -> ExperimentCheckpoint:
        if self.would_duplicate(case_id):
            raise ValueError(f"case already consumed: {case_id}")
        if evidence_digest and self.has_evidence_digest(evidence_digest):
            raise ValueError(f"duplicate evidence digest: {evidence_digest}")
        consumed = list(self.consumed_case_ids) + [case_id]
        ordering = list(self.ordering) + [case_id]
        digests = dict(self.evidence_digests)
        if evidence_digest:
            digests[case_id] = evidence_digest
        assignments = dict(self.assignment_map)
        assignments[case_id] = assignment or self.assignment
        state = dict(self.sampler_state)
        if sampler_state:
            state.update(sampler_state)
        return self.model_copy(
            update={
                "consumed_case_ids": consumed,
                "ordering": ordering,
                "evidence_digests": digests,
                "assignment_map": assignments,
                "sampler_state": state,
            }
        )

    def resume_cursor(self) -> int:
        return len(self.consumed_case_ids)

    def remaining(self, corpus: Sequence[str]) -> list[str]:
        seen = set(self.consumed_case_ids)
        return [case_id for case_id in corpus if case_id not in seen]


def lineage_digest(checkpoint: ExperimentCheckpoint) -> str:
    return content_digest(
        {
            "experiment_id": checkpoint.experiment_id,
            "checkpoint_id": checkpoint.checkpoint_id,
            "assignment": checkpoint.assignment,
            "consumed_case_ids": checkpoint.consumed_case_ids,
            "ordering": checkpoint.ordering,
            "evidence_digests": checkpoint.evidence_digests,
            "sampler_state": checkpoint.sampler_state,
        }
    )
