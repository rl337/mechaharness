"""Optional harness-health snapshots for cleanup evidence.

WalkingLabs L02/L12 treat harness debt like code debt
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-02-what-a-harness-actually-is/,
https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/).

Cleanup scheduling stays client-owned; MechaHarness supplies the schema::

    >>> from mechaharness.harness_health import HarnessHealthSnapshot, needs_cleanup
    >>> snap = HarnessHealthSnapshot(
    ...     unused_extensions=["acme:old"],
    ...     dead_soft_points=["legacy_tool"],
    ...     unexercised_routes=["retry_orphan"],
    ... )
    >>> needs_cleanup(snap)
    True
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HarnessHealthSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1"
    unused_extensions: list[str] = Field(default_factory=list)
    dead_soft_points: list[str] = Field(default_factory=list)
    stale_bindings: list[str] = Field(default_factory=list)
    unexercised_routes: list[str] = Field(default_factory=list)
    recurring_linkage_warnings: list[str] = Field(default_factory=list)
    ablation_evidence_refs: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


def needs_cleanup(snapshot: HarnessHealthSnapshot) -> bool:
    return bool(
        snapshot.unused_extensions
        or snapshot.dead_soft_points
        or snapshot.stale_bindings
        or snapshot.unexercised_routes
        or snapshot.recurring_linkage_warnings
    )
