"""Verification selection policy — distinct from JudgementPolicy.

Prefer deterministic oracles when available; scale effort by consequence and
uncertainty. Completion may depend on verification state via OutcomeContract.

In *Building verification loops in Claude Code with skills*, the Claude
developer blog suggests that “answer generated” is not the same as “task
complete”, and that deterministic checks should close the loop before done
(https://claude.com/blog/building-verification-loops-in-claude-code-with-skills).
Prefer executable/schema oracles; exhaust checks when consequence is high::

    >>> from mechaharness.graph import GraphNode, VerificationOracle
    >>> from mechaharness.outcome_contract import OutcomeContract
    >>> from mechaharness.verification_policy import DefaultVerificationPolicy
    >>> policy = DefaultVerificationPolicy()
    >>> node = GraphNode(id="page", kind="edit")
    >>> oracles = [
    ...     VerificationOracle(name="schema", strength="schema"),
    ...     VerificationOracle(name="lighthouse", strength="executable"),
    ... ]
    >>> plan = policy.plan(node, oracles, confidence=0.95)
    >>> plan.oracle_names
    ['lighthouse']
    >>> plan = policy.plan(node, oracles, consequence="critical")
    >>> sorted(plan.oracle_names)
    ['lighthouse', 'schema']
    >>> result = policy.verify(
    ...     node,
    ...     oracles=oracles,
    ...     verifiers=[lambda _n: (True, {"score": 92})],
    ...     outcome=OutcomeContract(
    ...         require_verification=True, acceptance=["score>=90"],
    ...     ),
    ...     answer_generated=True,
    ... )
    >>> result.passed, result.completion
    (True, 'complete')
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.graph import (
    GraphNode,
    VerificationOracle,
    select_strongest_oracle,
    verify_node,
)
from mechaharness.outcome_contract import CompletionState, OutcomeContract

Verifier = Callable[[GraphNode], tuple[bool, dict[str, Any]]]


class VerificationPlan(BaseModel):
    """Selected verification set for a node or graph phase."""

    model_config = ConfigDict(extra="allow")

    oracle_names: list[str] = Field(default_factory=list)
    exhaustive: bool = False
    reason: str = ""
    estimated_cost: float | None = None


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    passed: bool
    evidence: dict[str, Any] = Field(default_factory=dict)
    plan: VerificationPlan | None = None
    completion: CompletionState | None = None


class VerificationPolicy(ABC):
    """Select and execute appropriate verification."""

    @abstractmethod
    def plan(
        self,
        node: GraphNode,
        oracles: Sequence[VerificationOracle],
        *,
        consequence: str | None = None,
        confidence: float | None = None,
    ) -> VerificationPlan:
        ...

    @abstractmethod
    def verify(
        self,
        node: GraphNode,
        *,
        oracles: Sequence[VerificationOracle],
        verifiers: Sequence[Verifier],
        outcome: OutcomeContract | None = None,
        consequence: str | None = None,
        confidence: float | None = None,
        answer_generated: bool = False,
    ) -> VerificationResult:
        ...


class DefaultVerificationPolicy(VerificationPolicy):
    """Smallest sufficient set via strongest oracle; exhaustive for high consequence."""

    HIGH_CONSEQUENCE = frozenset({"high", "critical", "irreversible"})

    def plan(
        self,
        node: GraphNode,
        oracles: Sequence[VerificationOracle],
        *,
        consequence: str | None = None,
        confidence: float | None = None,
    ) -> VerificationPlan:
        del node
        exhaustive = (consequence or "").lower() in self.HIGH_CONSEQUENCE
        if exhaustive:
            return VerificationPlan(
                oracle_names=[o.name for o in oracles],
                exhaustive=True,
                reason="high_consequence",
            )
        strongest = select_strongest_oracle(oracles)
        if strongest is None:
            return VerificationPlan(oracle_names=[], reason="no_oracles")
        # Prefer a single strongest oracle when confidence is adequate.
        if confidence is not None and confidence >= 0.9 and strongest.strength != "model_judgment":
            return VerificationPlan(
                oracle_names=[strongest.name],
                reason="high_confidence_strongest",
            )
        return VerificationPlan(
            oracle_names=[strongest.name],
            reason="smallest_sufficient",
        )

    def verify(
        self,
        node: GraphNode,
        *,
        oracles: Sequence[VerificationOracle],
        verifiers: Sequence[Verifier],
        outcome: OutcomeContract | None = None,
        consequence: str | None = None,
        confidence: float | None = None,
        answer_generated: bool = False,
    ) -> VerificationResult:
        plan = self.plan(
            node, oracles, consequence=consequence, confidence=confidence
        )
        selected = {o.name for o in oracles if o.name in plan.oracle_names}
        # When exhaustive, use all verifiers; else keep order but still run provided set.
        active = verifiers if plan.exhaustive or not selected else verifiers
        passed, evidence = verify_node(node, active) if active else (True, {})
        completion = None
        if outcome is not None:
            completion = outcome.evaluate(
                answer_generated=answer_generated,
                verification_passed=passed,
            )
        return VerificationResult(
            passed=passed,
            evidence=evidence,
            plan=plan,
            completion=completion,
        )
