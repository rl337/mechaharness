"""Loop-health / verification-debt signals for long autonomous loops.

WalkingLabs L13 notes long loops accumulate verification and comprehension debt
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-13-loop-engineering/).

::

    >>> from mechaharness.loop_health import LoopHealthSignals, should_wind_down
    >>> signals = LoopHealthSignals(
    ...     iterations_since_independent_verification=6,
    ...     repeated_failure_class_count=3,
    ...     unresolved_assumptions=2,
    ... )
    >>> should_wind_down(signals, max_unverified_iterations=5)
    True
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoopHealthSignals(BaseModel):
    model_config = ConfigDict(extra="allow")

    iterations_since_independent_verification: int = 0
    context_growth_tokens: int = 0
    compaction_churn: int = 0
    repeated_failure_class_count: int = 0
    cost_trend_usd: float | None = None
    human_review_age_ms: float | None = None
    unresolved_assumptions: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


def should_wind_down(
    signals: LoopHealthSignals,
    *,
    max_unverified_iterations: int = 5,
    max_repeated_failures: int = 3,
    max_unresolved_assumptions: int = 5,
) -> bool:
    if signals.iterations_since_independent_verification >= max_unverified_iterations:
        return True
    if signals.repeated_failure_class_count >= max_repeated_failures:
        return True
    if signals.unresolved_assumptions >= max_unresolved_assumptions:
        return True
    return False
