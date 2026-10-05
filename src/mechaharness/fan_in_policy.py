"""First-class fan-in acceptance policies for parallel branches.

WalkingLabs P08 requires named merge/acceptance strategies at fan-in
(https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/).

MechaHarness supports ALL/ANY/quorum/predicate strategies (judge/human remain
host-supplied callables)::

    >>> from mechaharness.fan_in_policy import FanInPolicy, accept_fan_in
    >>> policy = FanInPolicy(strategy="quorum", quorum=2)
    >>> accept_fan_in(policy, results=[True, True, False])
    True
    >>> accept_fan_in(FanInPolicy(strategy="all"), results=[True, False])
    False
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FanInStrategy = Literal[
    "all",
    "any",
    "quorum",
    "weighted",
    "predicate",
    "judge",
    "human",
    "custom",
]


class FanInPolicy(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1"
    strategy: FanInStrategy = "all"
    quorum: int | None = None
    weights: list[float] = Field(default_factory=list)
    weighted_threshold: float = 0.5
    predicate_name: str | None = None


def accept_fan_in(
    policy: FanInPolicy,
    *,
    results: Sequence[bool],
    scores: Sequence[float] | None = None,
    predicate: Callable[[Sequence[bool]], bool] | None = None,
    custom: Callable[[Sequence[bool]], bool] | None = None,
) -> bool:
    vals = list(results)
    if policy.strategy == "all":
        return bool(vals) and all(vals)
    if policy.strategy == "any":
        return any(vals)
    if policy.strategy == "quorum":
        need = policy.quorum or max(1, (len(vals) // 2) + 1)
        return sum(1 for v in vals if v) >= need
    if policy.strategy == "weighted":
        sc = list(scores or [1.0 if v else 0.0 for v in vals])
        w = list(policy.weights) or [1.0] * len(sc)
        total = sum(a * b for a, b in zip(sc, w))
        denom = sum(w) or 1.0
        return (total / denom) >= policy.weighted_threshold
    if policy.strategy == "predicate":
        if predicate is None:
            raise ValueError("predicate strategy requires predicate callable")
        return bool(predicate(vals))
    if policy.strategy in ("judge", "human", "custom"):
        if custom is None:
            raise ValueError(f"{policy.strategy} strategy requires custom callable")
        return bool(custom(vals))
    raise ValueError(f"unknown fan-in strategy {policy.strategy!r}")


def describe_fan_in(policy: FanInPolicy) -> dict[str, Any]:
    return policy.model_dump(mode="json")
