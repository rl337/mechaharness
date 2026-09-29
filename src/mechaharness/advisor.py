"""Sparse, non-binding advisor counsel (distinct from GraphEscalation).

A subagent owns delegated work; an advisor observes decision state and returns
guidance while the caller retains ownership. Model escalation replaces the
executor; advising lets the existing executor continue.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AdvisorTrigger = Literal[
    "consequential_planning",
    "repeated_failure",
    "unresolved_hypothesis",
    "uncertainty_threshold",
    "high_consequence_completion",
    "model_initiated",
    "policy_initiated",
    "graph_initiated",
    "user_initiated",
]


class AdvisorContextContract(BaseModel):
    """Explicit context supplied to an advisor (not automatically full history)."""

    model_config = ConfigDict(extra="allow")

    include_full_history: bool = False
    summary: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    retrieved_state: dict[str, Any] = Field(default_factory=dict)
    decision_state: dict[str, Any] = Field(default_factory=dict)


class AdvisorRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    trigger: AdvisorTrigger
    context: AdvisorContextContract = Field(default_factory=AdvisorContextContract)
    required_capability: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdvisorGuidance(BaseModel):
    """Non-binding counsel; executor may reject or adapt."""

    model_config = ConfigDict(extra="allow")

    recommendations: list[str] = Field(default_factory=list)
    uncertainty: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    requested_evidence: list[str] = Field(default_factory=list)
    proposed_next_actions: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class AdvisorObservation(BaseModel):
    """Trace record for advisor use and whether advice was followed."""

    model_config = ConfigDict(extra="allow")

    trigger: AdvisorTrigger
    advisor_id: str
    request: AdvisorRequest
    guidance: AdvisorGuidance | None = None
    latency_ms: float | None = None
    resource_cost: dict[str, Any] = Field(default_factory=dict)
    followed: bool | None = None
    outcome: str | None = None
    error: str | None = None


class Advisor(ABC):
    """Accepts structured decision state; returns non-binding guidance."""

    advisor_id: str = "advisor"

    @abstractmethod
    async def advise(self, request: AdvisorRequest) -> AdvisorGuidance:
        ...


class RejectAdvisor(Advisor):
    """Default: advisor unavailable; callers apply fallback policy."""

    advisor_id = "reject"

    async def advise(self, request: AdvisorRequest) -> AdvisorGuidance:
        del request
        return AdvisorGuidance(
            recommendations=[],
            assumptions=["advisor_unavailable"],
            proposed_next_actions=["continue_without_advisor"],
        )


class AdvisorPolicy(ABC):
    """Decide whether consultation is warranted and what context to supply."""

    @abstractmethod
    def should_consult(
        self,
        *,
        trigger: AdvisorTrigger | None = None,
        repeated_failures: int = 0,
        uncertainty: float | None = None,
        consequence: str | None = None,
        budget_remaining: int | None = None,
    ) -> bool:
        ...

    @abstractmethod
    def context_for(self, trigger: AdvisorTrigger, **kwargs: Any) -> AdvisorContextContract:
        ...

    def on_advisor_failure(self) -> Literal["continue", "abort", "escalate"]:
        return "continue"


class DefaultAdvisorPolicy(AdvisorPolicy):
    """Sparse triggers with optional rate limit."""

    def __init__(
        self,
        *,
        max_consultations: int = 3,
        uncertainty_threshold: float = 0.7,
        failure_threshold: int = 2,
    ) -> None:
        self.max_consultations = max_consultations
        self.uncertainty_threshold = uncertainty_threshold
        self.failure_threshold = failure_threshold
        self._used = 0

    def should_consult(
        self,
        *,
        trigger: AdvisorTrigger | None = None,
        repeated_failures: int = 0,
        uncertainty: float | None = None,
        consequence: str | None = None,
        budget_remaining: int | None = None,
    ) -> bool:
        if budget_remaining is not None and budget_remaining <= 0:
            return False
        if self._used >= self.max_consultations:
            return False
        if trigger in {
            "consequential_planning",
            "high_consequence_completion",
            "user_initiated",
        }:
            return True
        if repeated_failures >= self.failure_threshold:
            return True
        if uncertainty is not None and uncertainty >= self.uncertainty_threshold:
            return True
        if (consequence or "").lower() in {"high", "critical"}:
            return True
        return trigger in {"repeated_failure", "unresolved_hypothesis", "uncertainty_threshold"}

    def context_for(self, trigger: AdvisorTrigger, **kwargs: Any) -> AdvisorContextContract:
        return AdvisorContextContract(
            include_full_history=False,
            summary=kwargs.get("summary"),
            evidence_refs=list(kwargs.get("evidence_refs") or []),
            trace_refs=list(kwargs.get("trace_refs") or []),
            artifact_refs=list(kwargs.get("artifact_refs") or []),
            retrieved_state=dict(kwargs.get("retrieved_state") or {}),
            decision_state=dict(kwargs.get("decision_state") or {"trigger": trigger}),
        )

    def record_consultation(self) -> None:
        self._used += 1


async def consult_advisor(
    advisor: Advisor,
    policy: AdvisorPolicy,
    request: AdvisorRequest,
    *,
    observations: list[AdvisorObservation] | None = None,
) -> AdvisorGuidance | None:
    """Invoke advisor when policy allows; record observation; never transfer ownership."""
    if not policy.should_consult(trigger=request.trigger):
        return None
    try:
        guidance = await advisor.advise(request)
        if isinstance(policy, DefaultAdvisorPolicy):
            policy.record_consultation()
        if observations is not None:
            observations.append(
                AdvisorObservation(
                    trigger=request.trigger,
                    advisor_id=getattr(advisor, "advisor_id", "advisor"),
                    request=request,
                    guidance=guidance,
                )
            )
        return guidance
    except Exception as exc:  # noqa: BLE001
        if observations is not None:
            observations.append(
                AdvisorObservation(
                    trigger=request.trigger,
                    advisor_id=getattr(advisor, "advisor_id", "advisor"),
                    request=request,
                    error=str(exc),
                )
            )
        fallback = policy.on_advisor_failure()
        if fallback == "abort":
            raise
        return None
