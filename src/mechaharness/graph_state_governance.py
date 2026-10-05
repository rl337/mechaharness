"""Ownership and mutability rules for graph-shared state fields.

WalkingLabs L14 notes that graph metrics/targets need ownership and frozen
semantics
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/).

MechaHarness reuses capability-like field governance::

    >>> from mechaharness.graph_state_governance import (
    ...     FieldGovernance, GraphStateGovernance, authorize_write,
    ... )
    >>> gov = GraphStateGovernance(fields={
    ...     "quality_target": FieldGovernance(
    ...         owner="ops", writers=["ops"], mutable=False
    ...     ),
    ... })
    >>> authorize_write(gov, field="quality_target", actor="agent")
    False
    >>> authorize_write(gov, field="quality_target", actor="ops")
    False
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FieldGovernance(BaseModel):
    model_config = ConfigDict(extra="allow")

    owner: str
    readers: list[str] = Field(default_factory=list)
    writers: list[str] = Field(default_factory=list)
    mutable: bool = True
    change_preconditions: list[str] = Field(default_factory=list)


class GraphStateGovernance(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1"
    fields: dict[str, FieldGovernance] = Field(default_factory=dict)

    def get(self, field: str) -> FieldGovernance | None:
        return self.fields.get(field)


def authorize_write(
    governance: GraphStateGovernance,
    *,
    field: str,
    actor: str,
    preconditions_met: list[str] | None = None,
) -> bool:
    rule = governance.get(field)
    if rule is None:
        return True
    if not rule.mutable:
        return False
    if rule.writers and actor not in rule.writers and actor != rule.owner:
        return False
    needed = set(rule.change_preconditions)
    if needed and not needed.issubset(set(preconditions_met or [])):
        return False
    return True


def authorize_read(
    governance: GraphStateGovernance, *, field: str, actor: str
) -> bool:
    rule = governance.get(field)
    if rule is None:
        return True
    if not rule.readers:
        return True
    return actor in rule.readers or actor == rule.owner


def describe_governance(governance: GraphStateGovernance) -> dict[str, Any]:
    return governance.model_dump(mode="json")
