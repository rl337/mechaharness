"""Labeled anchor evidence requirements for high-autonomy graphs.

WalkingLabs L14 asks for external anchors that prevent mutually reinforcing
drift
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/).

MechaHarness lets outcome/verification contracts require labeled anchors::

    >>> from mechaharness.anchor_evidence import (
    ...     AnchorRequirement, AnchorEvidence, anchors_satisfied,
    ... )
    >>> req = AnchorRequirement(kinds=["external_observation"], min_count=1)
    >>> anchors_satisfied(req, [
    ...     AnchorEvidence(kind="external_observation", ref="obs:1"),
    ... ])
    True
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AnchorKind = Literal[
    "real_world_outcome",
    "ground_truth_dataset",
    "external_observation",
    "human_spot_check",
]


class AnchorEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: AnchorKind
    ref: str
    summary: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class AnchorRequirement(BaseModel):
    model_config = ConfigDict(extra="allow")

    kinds: list[AnchorKind] = Field(default_factory=list)
    min_count: int = 1
    periodic: bool = False


def anchors_satisfied(
    requirement: AnchorRequirement, anchors: list[AnchorEvidence]
) -> bool:
    if not requirement.kinds:
        return len(anchors) >= requirement.min_count
    matched = [a for a in anchors if a.kind in requirement.kinds]
    return len(matched) >= requirement.min_count


def missing_anchor_kinds(
    requirement: AnchorRequirement, anchors: list[AnchorEvidence]
) -> list[str]:
    present = {a.kind for a in anchors}
    return [k for k in requirement.kinds if k not in present]
