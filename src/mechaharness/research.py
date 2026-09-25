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


# America's-Test-Kitchen-style searchable dimensions (EXP-02)
ATK_SEARCH_DIMENSIONS = (
    "model",
    "inference_primitive",
    "question_wording",
    "batching",
    "calibrated_thresholds",
    "escalation",
    "routing_affinity",
    "context_strategy",
    "graph_composition",
    "retrieval_strategy",
    "memory_consolidation",
    "cache_layout",
    "topology_maps",
    "dependency_removal",
    "fan_out_width",
    "reduction_depth",
    "verification_strategy",
    "decision_backend",
)


class EvalProtocol(BaseModel):
    """Frozen evaluation protocol (EXP-04) — set before runs."""

    model_config = ConfigDict(extra="allow")

    task_split: str
    primary_metric: str = "task_success_rate"
    regression_margin: float = 0.0
    safety_constraints: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    stats_method: str = "noninferiority"
    held_out_protected: bool = True
    search_dimensions: list[str] = Field(
        default_factory=lambda: list(ATK_SEARCH_DIMENSIONS)
    )


class ResearchCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid4()))
    hypothesis: str
    change_set: dict[str, Any] = Field(default_factory=dict)
    status: CandidateStatus = CandidateStatus.PROPOSED
    metrics: dict[str, float] = Field(default_factory=dict)
    lineage: list[str] = Field(default_factory=list)
    notes: str = ""
    ablations: dict[str, float] = Field(default_factory=dict)


class ResearchBudget(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_candidates: int = 8
    max_evals: int = 20


class AtkEvaluationReport(BaseModel):
    """Falsifiable recipe report (EXP-02/04)."""

    model_config = ConfigDict(extra="allow")

    protocol_split: str
    baseline_metric: float
    candidates: list[ResearchCandidate] = Field(default_factory=list)
    rejected_cheap_failures: list[str] = Field(default_factory=list)
    promoted_id: str | None = None
    negative_results: list[str] = Field(default_factory=list)
    topology_metrics: dict[str, Any] = Field(default_factory=dict)


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
        self._authoritative_evaluator: Callable[..., Any] | None = None

    def set_authoritative_evaluator(self, fn: Callable[..., Any]) -> None:
        """Production evaluator — candidates must not replace this (EXP-03)."""
        self._authoritative_evaluator = fn

    def propose(self, hypothesis: str, change_set: Mapping[str, Any]) -> ResearchCandidate:
        if "authoritative_evaluator" in change_set:
            raise RuntimeError("candidates cannot modify authoritative evaluator")
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
        ablations: Mapping[str, float] | None = None,
        whole_task_cost: float | None = None,
    ) -> ResearchCandidate:
        if self._evals >= self.budget.max_evals:
            raise RuntimeError("research eval budget exhausted")
        self._evals += 1
        candidate.status = CandidateStatus.EVALUATING
        candidate.metrics[self.protocol.primary_metric] = metric
        if ablations:
            candidate.ablations = dict(ablations)
        if whole_task_cost is not None:
            candidate.metrics["whole_task_cost"] = whole_task_cost
        if not safety_ok:
            candidate.status = CandidateStatus.REJECTED
            candidate.notes = "safety_constraint_failed"
            return candidate
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

    def report(self) -> AtkEvaluationReport:
        rejected_cheap = [
            c.id
            for c in self.candidates
            if c.status == CandidateStatus.REJECTED
            and c.metrics.get("whole_task_cost") is not None
            and c.metrics.get("whole_task_cost", 0) < 1.0
            and c.notes == "worse_than_baseline"
        ]
        negatives = [c.hypothesis for c in self.candidates if c.status == CandidateStatus.REJECTED]
        return AtkEvaluationReport(
            protocol_split=self.protocol.task_split,
            baseline_metric=self.baseline_metric,
            candidates=list(self.candidates),
            rejected_cheap_failures=rejected_cheap,
            promoted_id=self.promoted.id if self.promoted else None,
            negative_results=negatives,
        )


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
