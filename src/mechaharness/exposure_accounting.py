"""Exposure accounting across harness experiments (MH-MHRL-14).

Equal rollout counts do not imply equal exposure — different harnesses produce
different model calls, tokens, and tool use
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#how-much-each-run-saw)::

    >>> from mechaharness.exposure_accounting import ExposureLedger, ExposureSample
    >>> ledger = ExposureLedger()
    >>> ledger.record(ExposureSample(
    ...     arm="treatment", tasks=1, rollouts=1, model_calls=4, tokens_out=800,
    ... ))
    >>> ledger.record(ExposureSample(
    ...     arm="control", tasks=1, rollouts=1, model_calls=1, tokens_out=100,
    ... ))
    >>> summary = ledger.summarize()
    >>> summary["arms"]["treatment"]["model_calls"]
    4.0
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExposureSample(BaseModel):
    model_config = ConfigDict(extra="allow")

    arm: str
    tasks: int = 0
    rollouts: int = 0
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: int = 0
    wall_time_ms: float = 0.0
    cost_usd: float = 0.0
    accepted_training_targets: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


class ExposureLedger(BaseModel):
    model_config = ConfigDict(extra="allow")

    samples: list[ExposureSample] = Field(default_factory=list)

    def record(self, sample: ExposureSample) -> None:
        self.samples.append(sample)

    def summarize(self) -> dict[str, Any]:
        arms: dict[str, dict[str, float]] = {}
        for sample in self.samples:
            bucket = arms.setdefault(
                sample.arm,
                {
                    "tasks": 0.0,
                    "rollouts": 0.0,
                    "model_calls": 0.0,
                    "tokens_in": 0.0,
                    "tokens_out": 0.0,
                    "tool_calls": 0.0,
                    "wall_time_ms": 0.0,
                    "cost_usd": 0.0,
                    "accepted_training_targets": 0.0,
                },
            )
            bucket["tasks"] += sample.tasks
            bucket["rollouts"] += sample.rollouts
            bucket["model_calls"] += sample.model_calls
            bucket["tokens_in"] += sample.tokens_in
            bucket["tokens_out"] += sample.tokens_out
            bucket["tool_calls"] += sample.tool_calls
            bucket["wall_time_ms"] += sample.wall_time_ms
            bucket["cost_usd"] += sample.cost_usd
            bucket["accepted_training_targets"] += sample.accepted_training_targets
        return {"arm_count": len(arms), "arms": arms}


def exposure_from_mapping(arm: str, values: Mapping[str, Any]) -> ExposureSample:
    return ExposureSample(
        arm=arm,
        tasks=int(values.get("tasks") or 0),
        rollouts=int(values.get("rollouts") or 0),
        model_calls=int(values.get("model_calls") or 0),
        tokens_in=int(values.get("tokens_in") or 0),
        tokens_out=int(values.get("tokens_out") or 0),
        tool_calls=int(values.get("tool_calls") or 0),
        wall_time_ms=float(values.get("wall_time_ms") or 0.0),
        cost_usd=float(values.get("cost_usd") or 0.0),
        accepted_training_targets=int(values.get("accepted_training_targets") or 0),
    )
