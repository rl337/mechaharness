"""Delegation policy: inline versus child / subgraph execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.capability_envelope import CapabilityEnvelope

DelegationChoice = Literal["inline", "child", "subgraph"]


class DelegationRequest(BaseModel):
    """Signals used to choose delegation shape."""

    model_config = ConfigDict(extra="allow")

    task_kind: str = "generic"
    dependency_count: int = 0
    context_tokens: int = 0
    context_pollution_risk: float = 0.0
    parallelism: int = 1
    independence_required: bool = False
    latency_budget_ms: int | None = None
    estimated_child_cost: float | None = None
    estimated_inline_cost: float | None = None
    coordination_cost: float = 0.0
    parent_envelope: CapabilityEnvelope | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DelegationDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    choice: DelegationChoice
    reason: str
    child_envelope: CapabilityEnvelope | None = None
    template_name: str | None = None


class DelegationPolicy(ABC):
    """Choose inline versus child/subgraph execution."""

    @abstractmethod
    def decide(self, request: DelegationRequest) -> DelegationDecision:
        ...


class DefaultDelegationPolicy(DelegationPolicy):
    """Heuristic: prefer child when independence/pollution/parallelism dominate."""

    def decide(self, request: DelegationRequest) -> DelegationDecision:
        if request.independence_required or request.context_pollution_risk >= 0.6:
            envelope = None
            if request.parent_envelope is not None:
                envelope = request.parent_envelope.narrow(
                    parent_state_version=request.metadata.get("parent_state_version")
                )
            return DelegationDecision(
                choice="child",
                reason="independence_or_pollution",
                child_envelope=envelope,
            )
        if request.parallelism > 1:
            return DelegationDecision(
                choice="subgraph",
                reason="parallelism",
                template_name="fan_out_aggregate",
                child_envelope=(
                    request.parent_envelope.narrow()
                    if request.parent_envelope is not None
                    else None
                ),
            )
        child_cost = request.estimated_child_cost
        inline_cost = request.estimated_inline_cost
        if (
            child_cost is not None
            and inline_cost is not None
            and child_cost + request.coordination_cost < inline_cost
        ):
            return DelegationDecision(
                choice="child",
                reason="lower_total_cost",
                child_envelope=(
                    request.parent_envelope.narrow()
                    if request.parent_envelope is not None
                    else None
                ),
            )
        return DelegationDecision(choice="inline", reason="default_inline")
