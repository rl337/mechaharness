"""Stop contracts for repeating graph / subgraph work.

``StopContract`` is the inspiration-facing name for the fields already modeled
by :class:`~mechaharness.convergence.ConvergenceContract`, plus explicit
trigger / continuation / success / abort / progress semantics required for
linkage validation. Repeating nodes without a stop contract (and without
``persistent_service``) fail linkage.

In *Loop engineering: Getting started with loops*, the Claude developer blog
suggests every repeating cycle declare trigger, continuation, success/abort,
progress, and budgets rather than an open-ended chat turn
(https://claude.com/blog/getting-started-with-loops)::

    >>> from mechaharness.stop_contract import StopContract
    >>> goal = StopContract(
    ...     trigger="user_or_schedule",
    ...     continuation_condition="goal_unmet_and_budget_ok",
    ...     success_condition="lighthouse_score>=90",
    ...     abort_condition="max_iterations_or_wall_clock",
    ...     progress_signal="score_delta",
    ...     carried_state_keys=["best_score", "last_diff"],
    ...     max_iterations=5,
    ...     max_elapsed_ms=30 * 60_000,
    ... )
    >>> goal.is_bounded()
    True
    >>> guard = goal.guard()
    >>> guard.contract.max_iterations
    5
    >>> # Persistent service loops are explicit — they skip bounded validation.
    >>> StopContract(mode="persistent_service").is_bounded()
    False
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.convergence import ConvergenceContract, ConvergenceGuard

StopMode = Literal["bounded", "persistent_service"]


class StopContract(BaseModel):
    """Continuation, success, abort, progress, and resource limits for a loop."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    mode: StopMode = "bounded"
    trigger: str = "node_ready"
    continuation_condition: str = "not_terminal"
    success_condition: str = "acceptance_met"
    abort_condition: str = "budget_or_failure"
    progress_signal: str = "state_delta"
    carried_state_keys: list[str] = Field(default_factory=list)
    max_iterations: int = 8
    max_elapsed_ms: int | None = 60_000
    max_tokens: int | None = None
    max_spend_usd: float | None = None
    stagnation_window: int = 3
    parent_budget_share: float = 1.0

    def is_bounded(self) -> bool:
        return self.mode != "persistent_service"

    def to_convergence(self) -> ConvergenceContract:
        return ConvergenceContract(
            version=self.version,
            progress_measure=self.progress_signal,
            stagnation_window=self.stagnation_window,
            max_iterations=self.max_iterations,
            max_elapsed_ms=self.max_elapsed_ms,
            max_tokens=self.max_tokens,
            max_spend_usd=self.max_spend_usd,
            parent_budget_share=self.parent_budget_share,
        )

    @classmethod
    def from_convergence(cls, contract: ConvergenceContract, **kwargs: Any) -> StopContract:
        return cls(
            version=contract.version,
            progress_signal=contract.progress_measure,
            stagnation_window=contract.stagnation_window,
            max_iterations=contract.max_iterations,
            max_elapsed_ms=contract.max_elapsed_ms,
            max_tokens=contract.max_tokens,
            max_spend_usd=contract.max_spend_usd,
            parent_budget_share=contract.parent_budget_share,
            **kwargs,
        )

    def guard(self) -> ConvergenceGuard:
        return ConvergenceGuard(self.to_convergence())


# Re-export for hosts that already import convergence types.
__all__ = [
    "StopContract",
    "StopMode",
    "ConvergenceContract",
    "ConvergenceGuard",
]
