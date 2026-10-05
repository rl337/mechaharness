"""Isolated trials and capability/reliability aggregations.

Anthropic distinguishes ``pass@k`` (capability across attempts) from ``pass^k``
(reliability of repeated success)
(https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
τ-bench emphasizes end-state verification and repeatability
(https://arxiv.org/abs/2406.12045); HumanEval defines ``pass@k``
(https://arxiv.org/abs/2107.03374).

MechaHarness records trials without embedding application rubrics::

    >>> from mechaharness.eval_trial import Trial, pass_at_k, pass_caret_k
    >>> trials = [
    ...     Trial(trial_id="1", success=True, cost_usd=0.01, latency_ms=100),
    ...     Trial(trial_id="2", success=False, cost_usd=0.02, latency_ms=120),
    ...     Trial(trial_id="3", success=True, cost_usd=0.01, latency_ms=90),
    ... ]
    >>> pass_at_k(trials, k=2) > 0
    True
    >>> 0.0 <= pass_caret_k(trials, k=2) <= 1.0
    True
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.eval_evidence import Claim


class Trial(BaseModel):
    """One isolated evaluation attempt with cost/latency and claim set."""

    model_config = ConfigDict(extra="allow")

    trial_id: str
    success: bool
    cost_usd: float | None = None
    latency_ms: float | None = None
    claims: list[Claim] = Field(default_factory=list)
    run_id: str | None = None
    outcome_ref: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


def pass_at_k(trials: list[Trial], *, k: int) -> float:
    """Unbiased pass@k estimator over binary trial successes (HumanEval-style)."""
    n = len(trials)
    if n == 0 or k < 1:
        return 0.0
    c = sum(1 for t in trials if t.success)
    if n - c < k:
        return 1.0
    # 1 - C(n-c, k) / C(n, k)
    return 1.0 - (math.comb(n - c, k) / math.comb(n, k))


def pass_caret_k(trials: list[Trial], *, k: int) -> float:
    """Reliability: fraction of contiguous windows of size k that are all successes.

    For a simple i.i.d. reading, also equal to empirical success rate ** k when
    trials are shuffled; here we use the empirical rate^k for stability with
    small n (τ-bench-style reliability signal).
    """
    if not trials or k < 1:
        return 0.0
    rate = sum(1 for t in trials if t.success) / len(trials)
    return float(rate**k)


def trial_cost_rollup(trials: list[Trial]) -> dict[str, float]:
    costs = [t.cost_usd for t in trials if t.cost_usd is not None]
    latencies = [t.latency_ms for t in trials if t.latency_ms is not None]
    return {
        "total_cost_usd": float(sum(costs)) if costs else 0.0,
        "mean_latency_ms": float(sum(latencies) / len(latencies)) if latencies else 0.0,
        "trials": float(len(trials)),
    }
