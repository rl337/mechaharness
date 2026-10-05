"""Resume-cost telemetry for durable wake/rebuild measurement.

WalkingLabs L05/P03 ask that resume cost be observable
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-05-why-long-running-tasks-lose-continuity/,
https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-03-multi-session-continuity/).

::

    >>> from mechaharness.resume_cost import ResumeCostMetrics, summarize_resume_cost
    >>> m = ResumeCostMetrics(
    ...     wake_to_first_productive_ms=1200,
    ...     rebuild_tokens=400,
    ...     rebuild_tool_calls=3,
    ...     provider_loads=2,
    ...     revalidation_work=1,
    ...     replayed_events=12,
    ... )
    >>> summarize_resume_cost(m)["rebuild_tokens"]
    400
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResumeCostMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    wake_to_first_productive_ms: float | None = None
    rebuild_tokens: int = 0
    rebuild_tool_calls: int = 0
    provider_loads: int = 0
    revalidation_work: int = 0
    replayed_events: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


def summarize_resume_cost(metrics: ResumeCostMetrics) -> dict[str, Any]:
    return metrics.model_dump(mode="json")
