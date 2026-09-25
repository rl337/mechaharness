"""Executable-cycle convergence contracts (POL-03)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TerminalStatus = Literal[
    "success",
    "failure",
    "unknown",
    "no_progress",
    "exhaustion",
    "cancellation",
    "escalation",
]


class ConvergenceContract(BaseModel):
    """Versioned ceilings and progress rules for a bounded cycle."""

    model_config = ConfigDict(extra="allow")

    version: str
    progress_measure: str = "state_delta"
    dedupe_scope: str = "findings"
    stagnation_window: int = 3
    max_iterations: int = 8
    max_elapsed_ms: int | None = 60_000
    max_tokens: int | None = None
    max_spend_usd: float | None = None
    parent_budget_share: float = 1.0


class ConvergenceState(BaseModel):
    """Mutable progress tracker checked outside model inference."""

    model_config = ConfigDict(extra="allow")

    contract_version: str
    iterations: int = 0
    elapsed_ms: float = 0.0
    tokens: int = 0
    spend_usd: float = 0.0
    recent_fingerprints: list[str] = Field(default_factory=list)
    stagnant_ticks: int = 0
    terminal: TerminalStatus | None = None
    reason: str | None = None


class ConvergenceGuard:
    """Enforce POL-03 ceilings; never treat ceiling as task success."""

    def __init__(self, contract: ConvergenceContract) -> None:
        self.contract = contract
        self.state = ConvergenceState(contract_version=contract.version)

    def child(self, *, share: float | None = None) -> ConvergenceGuard:
        share = self.contract.parent_budget_share if share is None else share
        child_contract = self.contract.model_copy(
            update={
                "max_iterations": max(1, int(self.contract.max_iterations * share)),
                "max_elapsed_ms": (
                    None
                    if self.contract.max_elapsed_ms is None
                    else max(1, int(self.contract.max_elapsed_ms * share))
                ),
                "max_tokens": (
                    None
                    if self.contract.max_tokens is None
                    else max(1, int(self.contract.max_tokens * share))
                ),
                "max_spend_usd": (
                    None
                    if self.contract.max_spend_usd is None
                    else self.contract.max_spend_usd * share
                ),
            }
        )
        return ConvergenceGuard(child_contract)

    def tick(
        self,
        *,
        fingerprint: str | None = None,
        elapsed_ms: float = 0.0,
        tokens: int = 0,
        spend_usd: float = 0.0,
        cancelled: bool = False,
        escalate: bool = False,
        failed: bool = False,
    ) -> ConvergenceState:
        if self.state.terminal is not None:
            return self.state
        if cancelled:
            return self._stop("cancellation", "cancelled")
        if escalate:
            return self._stop("escalation", "escalated")
        if failed:
            return self._stop("failure", "failed")

        self.state.iterations += 1
        self.state.elapsed_ms += elapsed_ms
        self.state.tokens += tokens
        self.state.spend_usd += spend_usd

        if fingerprint is not None:
            if fingerprint in self.state.recent_fingerprints:
                self.state.stagnant_ticks += 1
            else:
                self.state.stagnant_ticks = 0
                self.state.recent_fingerprints.append(fingerprint)
                window = self.contract.stagnation_window
                if len(self.state.recent_fingerprints) > window:
                    self.state.recent_fingerprints = self.state.recent_fingerprints[
                        -window:
                    ]

        if self.state.iterations > self.contract.max_iterations:
            return self._stop("exhaustion", "max_iterations")
        if (
            self.contract.max_elapsed_ms is not None
            and self.state.elapsed_ms > self.contract.max_elapsed_ms
        ):
            return self._stop("exhaustion", "max_elapsed_ms")
        if (
            self.contract.max_tokens is not None
            and self.state.tokens > self.contract.max_tokens
        ):
            return self._stop("exhaustion", "max_tokens")
        if (
            self.contract.max_spend_usd is not None
            and self.state.spend_usd > self.contract.max_spend_usd
        ):
            return self._stop("exhaustion", "max_spend_usd")
        if (
            fingerprint is not None
            and self.state.stagnant_ticks >= self.contract.stagnation_window
        ):
            return self._stop("no_progress", "stagnation")

        return self.state

    def succeed(self) -> ConvergenceState:
        return self._stop("success", "completed")

    def _stop(self, status: TerminalStatus, reason: str) -> ConvergenceState:
        self.state.terminal = status
        self.state.reason = reason
        return self.state


def fingerprint_payload(value: Any) -> str:
    """Stable-ish fingerprint for progress dedupe (do not include timestamps)."""
    if isinstance(value, Mapping):
        items = sorted((str(k), fingerprint_payload(v)) for k, v in value.items())
        return repr(items)
    if isinstance(value, (list, tuple, set)):
        return repr([fingerprint_payload(v) for v in value])
    return repr(value)
