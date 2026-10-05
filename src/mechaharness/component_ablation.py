"""Standard component-ablation experiment shapes.

WalkingLabs L02 and P01 motivate ablating harness components against a matched
task corpus to learn what is load-bearing
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-02-what-a-harness-actually-is/,
https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-01-baseline-vs-minimal-harness/).

MechaHarness records ablation evidence for promotion/retirement::

    >>> from mechaharness.component_ablation import (
    ...     ComponentAblationExperiment, ablation_delta,
    ... )
    >>> exp = ComponentAblationExperiment(
    ...     baseline_fingerprint="harness:full",
    ...     disabled_component_ids=["advisor", "gotchas"],
    ...     task_corpus_ref="corpus:v1",
    ...     baseline_success_rate=0.8,
    ...     ablated_success_rate=0.5,
    ... )
    >>> ablation_delta(exp)["success_delta"]
    -0.3
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComponentAblationExperiment(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1"
    baseline_fingerprint: str
    disabled_component_ids: list[str] = Field(default_factory=list)
    task_corpus_ref: str
    baseline_success_rate: float
    ablated_success_rate: float
    baseline_cost_usd: float | None = None
    ablated_cost_usd: float | None = None
    baseline_latency_ms: float | None = None
    ablated_latency_ms: float | None = None
    confidence: float | None = None
    notes: str = ""


def ablation_delta(exp: ComponentAblationExperiment) -> dict[str, Any]:
    out: dict[str, Any] = {
        "success_delta": round(
            exp.ablated_success_rate - exp.baseline_success_rate, 10
        ),
        "disabled_component_ids": list(exp.disabled_component_ids),
    }
    if exp.baseline_cost_usd is not None and exp.ablated_cost_usd is not None:
        out["cost_delta"] = exp.ablated_cost_usd - exp.baseline_cost_usd
    if exp.baseline_latency_ms is not None and exp.ablated_latency_ms is not None:
        out["latency_delta"] = exp.ablated_latency_ms - exp.baseline_latency_ms
    return out
