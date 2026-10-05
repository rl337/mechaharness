"""WIP / back-pressure concurrency policy for graph execution.

WalkingLabs L07/L08 warn that agents overreach when work-in-progress is
unbounded; WIP=1 is a safe coding-agent default, not a universal constant
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-07-why-agents-overreach-and-under-finish/,
https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-08-why-feature-lists-are-harness-primitives/).

MechaHarness exposes injectable limits by graph, resource, write scope, or
consequence::

    >>> from mechaharness.work_in_progress_policy import WorkInProgressPolicy
    >>> policy = WorkInProgressPolicy(max_active_nodes=2, max_per_write_scope=1)
    >>> policy.allows(active_nodes=1, write_scope="repo:src", active_in_scope=0)
    True
    >>> policy.allows(active_nodes=2, write_scope="repo:src", active_in_scope=1)
    False
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkInProgressPolicy(BaseModel):
    """Back-pressure limits; hosts choose thresholds (no hard-coded WIP=1)."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    max_active_nodes: int | None = None
    max_per_resource_class: dict[str, int] = Field(default_factory=dict)
    max_per_write_scope: int | None = None
    max_per_consequence: dict[str, int] = Field(default_factory=dict)

    def allows(
        self,
        *,
        active_nodes: int,
        write_scope: str | None = None,
        active_in_scope: int = 0,
        resource_class: str | None = None,
        active_in_resource: int = 0,
        consequence: str | None = None,
        active_in_consequence: int = 0,
    ) -> bool:
        if self.max_active_nodes is not None and active_nodes >= self.max_active_nodes:
            return False
        if (
            write_scope is not None
            and self.max_per_write_scope is not None
            and active_in_scope >= self.max_per_write_scope
        ):
            return False
        if resource_class and resource_class in self.max_per_resource_class:
            if active_in_resource >= self.max_per_resource_class[resource_class]:
                return False
        if consequence and consequence in self.max_per_consequence:
            if active_in_consequence >= self.max_per_consequence[consequence]:
                return False
        return True

    def describe(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
