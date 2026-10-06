"""Comparable-run constraint parity (MH-MHRL-12).

FineEnvs found a train/eval output-token mismatch that taught behavior
evaluation later truncated
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#why-the-two-harbor-runs-declined).

MechaHarness snapshots constraint surfaces and reports material mismatches::

    >>> from mechaharness.run_parity import ParitySurface, compare_parity
    >>> a = ParitySurface(max_tokens=1024, temperature=0.0, tool_names=["Read"])
    >>> b = ParitySurface(max_tokens=512, temperature=0.0, tool_names=["Read"])
    >>> report = compare_parity(a, b)
    >>> report.comparable
    False
    >>> "max_tokens" in report.material_mismatches
    True
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.harness.base import HarnessConfig
from mechaharness.stop_contract import StopContract

MATERIAL_FIELDS = (
    "max_tokens",
    "max_turns",
    "temperature",
    "tool_names",
    "tool_budget",
    "timeout_ms",
    "context_limit",
    "retry_policy",
    "stop_policy",
    "sampling",
)


class ParitySurface(BaseModel):
    """Snapshot of constraints that must match for comparable evaluation runs."""

    model_config = ConfigDict(extra="allow")

    max_tokens: int | None = None
    max_turns: int | None = None
    temperature: float | None = None
    tool_names: list[str] = Field(default_factory=list)
    tool_budget: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = None
    context_limit: int | None = None
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    stop_policy: dict[str, Any] = Field(default_factory=dict)
    sampling: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

    def canonical(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "max_turns": self.max_turns,
            "temperature": self.temperature,
            "tool_names": sorted(self.tool_names),
            "tool_budget": dict(self.tool_budget),
            "timeout_ms": self.timeout_ms,
            "context_limit": self.context_limit,
            "retry_policy": dict(self.retry_policy),
            "stop_policy": dict(self.stop_policy),
            "sampling": dict(self.sampling),
        }


class ParityReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    comparable: bool = True
    mismatches: dict[str, dict[str, Any]] = Field(default_factory=dict)
    material_mismatches: list[str] = Field(default_factory=list)

    def raise_if_material(self) -> None:
        if self.material_mismatches:
            raise ValueError(
                "material run parity mismatches: " + ", ".join(self.material_mismatches)
            )


def parity_from_harness_config(
    config: HarnessConfig,
    *,
    envelope: CapabilityEnvelope | None = None,
    stop: StopContract | None = None,
    budget: BudgetPolicy | None = None,
    timeout_ms: int | None = None,
    context_limit: int | None = None,
    retry_policy: Mapping[str, Any] | None = None,
) -> ParitySurface:
    tool_names = list(envelope.tool_names) if envelope is not None else []
    tool_budget = dict(envelope.resource_budget) if envelope is not None else {}
    if budget is not None:
        tool_budget.setdefault("soft_limit", budget.soft_limit)
        tool_budget.setdefault("hard_limit", budget.hard_limit)
        tool_budget.setdefault("unit", budget.unit)
    stop_policy: dict[str, Any] = {}
    if stop is not None:
        stop_policy = {
            "max_iterations": stop.max_iterations,
            "max_elapsed_ms": stop.max_elapsed_ms,
            "mode": stop.mode,
        }
    sampling = {"temperature": config.temperature, "max_tokens": config.max_tokens}
    return ParitySurface(
        max_tokens=config.max_tokens,
        max_turns=config.max_turns,
        temperature=config.temperature,
        tool_names=tool_names,
        tool_budget=tool_budget,
        timeout_ms=timeout_ms,
        context_limit=context_limit,
        retry_policy=dict(retry_policy or {}),
        stop_policy=stop_policy,
        sampling=sampling,
    )


def compare_parity(a: ParitySurface, b: ParitySurface) -> ParityReport:
    left = a.canonical()
    right = b.canonical()
    mismatches: dict[str, dict[str, Any]] = {}
    material: list[str] = []
    for field in MATERIAL_FIELDS:
        if left.get(field) != right.get(field):
            mismatches[field] = {"a": left.get(field), "b": right.get(field)}
            material.append(field)
    return ParityReport(
        comparable=not material,
        mismatches=mismatches,
        material_mismatches=material,
    )
