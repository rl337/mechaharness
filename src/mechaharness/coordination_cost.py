"""Parallel coordination-cost telemetry for fan-out graphs.

WalkingLabs L14/P08 warn that parallelism must beat orchestration cost
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/,
https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/).

::

    >>> from mechaharness.coordination_cost import (
    ...     CoordinationCostMetrics, summarize_coordination_cost,
    ... )
    >>> m = CoordinationCostMetrics(
    ...     branch_count=4,
    ...     wall_clock_critical_path_ms=5000,
    ...     aggregate_cost_usd=0.4,
    ...     duplicated_context_tokens=1200,
    ...     fan_in_review_cost_usd=0.05,
    ... )
    >>> summarize_coordination_cost(m)["branch_count"]
    4
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CoordinationCostMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    branch_count: int = 0
    wall_clock_critical_path_ms: float | None = None
    aggregate_cost_usd: float | None = None
    duplicated_context_tokens: int = 0
    fan_in_review_cost_usd: float | None = None
    coordination_failures: int = 0
    quality_delta_vs_serial: float | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


def summarize_coordination_cost(metrics: CoordinationCostMetrics) -> dict[str, Any]:
    return metrics.model_dump(mode="json")
