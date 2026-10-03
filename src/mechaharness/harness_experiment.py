"""Harness changes as evaluable hypotheses (reqs 1, 14).

Cursor's *Continually improving our agent harness* and *CursorBench* treat
harness edits as experiments with online/offline evidence. Claude's harness
design post asks “what can I stop doing?” after each model upgrade::

    >>> from mechaharness.harness_experiment import (
    ...     HarnessExperiment, HarnessExperimentRunner,
    ... )
    >>> lab = HarnessExperimentRunner()
    >>> hyp = lab.propose(HarnessExperiment(
    ...     hypothesis="dynamic MCP tool loading cuts tokens without hurting success",
    ...     intervention="mcp_tools_as_discoverable_files",
    ...     failure_mode="context_bloat",
    ...     evidence="cursor.com/blog/dynamic-context-discovery",
    ...     expected_metrics={"task_success_rate": 0.0, "tokens": -0.4},
    ...     harness_version="2026.09",
    ... ))
    >>> hyp.to_trace_fields()["harness_intervention"]
    'mcp_tools_as_discoverable_files'
    >>> lab.evaluate(
    ...     hyp,
    ...     with_intervention=lambda: {"task_success_rate": 0.86, "tokens": 0.53},
    ...     without_intervention=lambda: {"task_success_rate": 0.85, "tokens": 1.0},
    ... ).status
    'retained'
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.research import EvalProtocol, ResearchLab

ExperimentStatus = Literal["proposed", "running", "retained", "retired", "rejected"]


class HarnessExperiment(BaseModel):
    """A/B or with/without comparison of an orchestration intervention."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid4()))
    hypothesis: str
    intervention: str
    failure_mode: str = ""
    evidence: str = ""
    expected_metrics: dict[str, float] = Field(default_factory=dict)
    harness_version: str = "1"
    assignment: str = "treatment"
    status: ExperimentStatus = "proposed"
    metrics: dict[str, float] = Field(default_factory=dict)
    control_metrics: dict[str, float] = Field(default_factory=dict)
    notes: str = ""

    def to_trace_fields(self) -> dict[str, Any]:
        return {
            "harness_experiment_id": self.id,
            "harness_version": self.harness_version,
            "harness_assignment": self.assignment,
            "harness_intervention": self.intervention,
        }


class HarnessExperimentRunner:
    """Evaluate harness hypotheses via ResearchLab-style offline eval."""

    def __init__(self, lab: ResearchLab | None = None) -> None:
        self.lab = lab or ResearchLab(
            protocol=EvalProtocol(task_split="harness_experiments")
        )
        self.experiments: list[HarnessExperiment] = []

    def propose(self, experiment: HarnessExperiment) -> HarnessExperiment:
        self.experiments.append(experiment)
        self.lab.propose(
            experiment.hypothesis,
            change_set={
                "intervention": experiment.intervention,
                "failure_mode": experiment.failure_mode,
                "evidence": experiment.evidence,
            },
        )
        return experiment

    def evaluate(
        self,
        experiment: HarnessExperiment,
        *,
        with_intervention: Callable[[], Mapping[str, float]],
        without_intervention: Callable[[], Mapping[str, float]],
        primary_metric: str = "task_success_rate",
    ) -> HarnessExperiment:
        experiment.status = "running"
        treatment = dict(with_intervention())
        control = dict(without_intervention())
        experiment.metrics = treatment
        experiment.control_metrics = control
        t = treatment.get(primary_metric)
        c = control.get(primary_metric)
        if t is not None and c is not None and t >= c:
            experiment.status = "retained"
        elif t is not None and c is not None:
            experiment.status = "retired"
        else:
            experiment.status = "rejected"
        return experiment

    def retirement_candidates(
        self, *, metric: str = "task_success_rate"
    ) -> list[HarnessExperiment]:
        return [
            e
            for e in self.experiments
            if e.status == "retired"
            or (
                e.metrics.get(metric) is not None
                and e.control_metrics.get(metric) is not None
                and e.metrics[metric] < e.control_metrics[metric]
            )
        ]
