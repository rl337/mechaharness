"""Bounded experimental auto-research (EXP-*) — isolated from production."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class CandidateStatus(str, Enum):
    PROPOSED = "proposed"
    EVALUATING = "evaluating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class EvalProtocol(BaseModel):
    """Frozen evaluation protocol (EXP-04) — set before runs."""

    model_config = ConfigDict(extra="allow")

    task_split: str
    primary_metric: str = "task_success_rate"
    regression_margin: float = 0.0
    safety_constraints: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    stats_method: str = "noninferiority"


class ResearchCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid4()))
    hypothesis: str
    change_set: dict[str, Any] = Field(default_factory=dict)
    status: CandidateStatus = CandidateStatus.PROPOSED
    metrics: dict[str, float] = Field(default_factory=dict)
    lineage: list[str] = Field(default_factory=list)
    notes: str = ""


class ResearchBudget(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_candidates: int = 8
    max_evals: int = 20


class ResearchLab:
    """Isolated research workflow with promote/rollback (EXP-01…04)."""

    def __init__(
        self,
        protocol: EvalProtocol,
        *,
        budget: ResearchBudget | None = None,
        baseline_metric: float = 0.0,
    ) -> None:
        self.protocol = protocol
        self.budget = budget or ResearchBudget()
        self.baseline_metric = baseline_metric
        self.candidates: list[ResearchCandidate] = []
        self.promoted: ResearchCandidate | None = None
        self._rollback: ResearchCandidate | None = None
        self._evals = 0

    def propose(self, hypothesis: str, change_set: Mapping[str, Any]) -> ResearchCandidate:
        if len(self.candidates) >= self.budget.max_candidates:
            raise RuntimeError("research candidate budget exhausted")
        cand = ResearchCandidate(hypothesis=hypothesis, change_set=dict(change_set))
        self.candidates.append(cand)
        return cand

    def evaluate(
        self,
        candidate: ResearchCandidate,
        *,
        metric: float,
        safety_ok: bool = True,
    ) -> ResearchCandidate:
        if self._evals >= self.budget.max_evals:
            raise RuntimeError("research eval budget exhausted")
        self._evals += 1
        candidate.status = CandidateStatus.EVALUATING
        candidate.metrics[self.protocol.primary_metric] = metric
        if not safety_ok:
            candidate.status = CandidateStatus.REJECTED
            candidate.notes = "safety_constraint_failed"
            return candidate
        # Cheaper-but-worse: reject if below baseline - margin
        floor = self.baseline_metric - self.protocol.regression_margin
        if metric < floor:
            candidate.status = CandidateStatus.REJECTED
            candidate.notes = "worse_than_baseline"
            return candidate
        if metric < self.baseline_metric:
            candidate.status = CandidateStatus.INCONCLUSIVE
            candidate.notes = "underpowered_or_noninferior_only"
            return candidate
        candidate.status = CandidateStatus.ACCEPTED
        return candidate

    def promote(self, candidate: ResearchCandidate) -> ResearchCandidate:
        if candidate.status != CandidateStatus.ACCEPTED:
            raise RuntimeError("only accepted candidates may be promoted")
        self._rollback = self.promoted
        self.promoted = candidate
        return candidate

    def rollback(self) -> ResearchCandidate | None:
        self.promoted = self._rollback
        self._rollback = None
        return self.promoted


def run_bounded_search(
    lab: ResearchLab,
    hypotheses: Sequence[tuple[str, Mapping[str, Any], float, bool]],
) -> list[ResearchCandidate]:
    """Inspect → hypothesis → evaluate → accept/reject loop."""
    results: list[ResearchCandidate] = []
    for hypothesis, change_set, metric, safety_ok in hypotheses:
        cand = lab.propose(hypothesis, change_set)
        results.append(lab.evaluate(cand, metric=metric, safety_ok=safety_ok))
    return results
