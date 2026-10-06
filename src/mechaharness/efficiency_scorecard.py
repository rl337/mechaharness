"""Multidimensional efficiency scorecard (MH-MHRL-19).

FineEnvs uses tool-call count as a simple efficiency signal; MechaHarness keeps
tokens, latency, coordination, and resume cost observable as separate dimensions
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#tool-calls-and-tokens)::

    >>> from mechaharness.efficiency_scorecard import build_efficiency_scorecard
    >>> card = build_efficiency_scorecard(
    ...     tool_calls=3,
    ...     tokens_out=1200,
    ...     latency_ms=4000,
    ...     coordination_cost=1.5,
    ...     resume_cost=0.2,
    ... )
    >>> card.dimensions["tool_calls"]
    3.0
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EfficiencyScorecard(BaseModel):
    """Composable efficiency dimensions (never collapsed silently)."""

    model_config = ConfigDict(extra="allow")

    dimensions: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)

    def as_metrics(self) -> dict[str, float]:
        return dict(self.dimensions)


def build_efficiency_scorecard(
    *,
    tool_calls: float | None = None,
    tokens_in: float | None = None,
    tokens_out: float | None = None,
    latency_ms: float | None = None,
    cost_usd: float | None = None,
    coordination_cost: float | None = None,
    resume_cost: float | None = None,
    topology_elapsed_ms: float | None = None,
    extra: Mapping[str, float] | None = None,
) -> EfficiencyScorecard:
    dims: dict[str, float] = {}
    for name, value in (
        ("tool_calls", tool_calls),
        ("tokens_in", tokens_in),
        ("tokens_out", tokens_out),
        ("latency_ms", latency_ms),
        ("cost_usd", cost_usd),
        ("coordination_cost", coordination_cost),
        ("resume_cost", resume_cost),
        ("topology_elapsed_ms", topology_elapsed_ms),
    ):
        if value is not None:
            dims[name] = float(value)
    if extra:
        dims.update({k: float(v) for k, v in extra.items()})
    return EfficiencyScorecard(dimensions=dims)
