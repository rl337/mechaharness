"""Provenance-bearing evaluator aggregation (MH-MHRL-07 / MH-MHRL-08).

FineEnvs refuses to invent a weighted combination of several verifier scores
and applies efficiency bonuses only after correctness
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#rewards).

MechaHarness requires an explicit ``ObjectivePolicy`` before collapsing
signals into a scalar::

    >>> from mechaharness.eval_evidence import Claim
    >>> from mechaharness.objective_policy import ObjectivePolicy, aggregate_objective
    >>> policy = ObjectivePolicy(
    ...     policy_id="demo:lexi",
    ...     version="1",
    ...     component_signals=["correct", "tokens"],
    ...     formula="lexicographic",
    ...     gates=["correct"],
    ...     lexicographic=["correct", "tokens"],
    ... )
    >>> claims = [
    ...     Claim(id="correct", statement="ok", status="pass"),
    ...     Claim(id="tokens", statement="budget", status="pass"),
    ... ]
    >>> result = aggregate_objective(policy, claims)
    >>> result.scored, result.scalar
    (True, 1.0)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.eval_evidence import Claim

FormulaKind = Literal["all_pass", "lexicographic", "gated_primary"]


class ObjectivePolicy(BaseModel):
    """Explicit aggregation recipe with gates and optional lexicographic order."""

    model_config = ConfigDict(extra="allow")

    policy_id: str
    version: str = "1"
    component_signals: list[str] = Field(default_factory=list)
    formula: str = "all_pass"
    bounds: dict[str, Any] = Field(default_factory=dict)
    gates: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    lexicographic: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


class ObjectiveResult(BaseModel):
    """Outcome of applying an ObjectivePolicy to claims or metrics."""

    model_config = ConfigDict(extra="allow")

    policy_id: str
    policy_version: str
    formula: str
    component_signals: list[str] = Field(default_factory=list)
    gates_satisfied: bool = True
    prerequisites_met: bool = True
    scored: bool = False
    unscorable: bool = False
    scalar: float | None = None
    gate_failures: list[str] = Field(default_factory=list)
    unmet_prerequisites: list[str] = Field(default_factory=list)
    component_status: dict[str, str] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)


def _status_map(claims: Sequence[Claim]) -> dict[str, str]:
    return {c.id: c.status for c in claims}


def aggregate_objective(
    policy: ObjectivePolicy,
    claims: Sequence[Claim],
    *,
    metrics: Mapping[str, float] | None = None,
) -> ObjectiveResult:
    """Aggregate claims/metrics under an explicit policy (no silent weights)."""
    status = _status_map(claims)
    metrics = dict(metrics or {})
    unmet = [p for p in policy.prerequisites if status.get(p) != "pass"]
    gate_failures = [
        g
        for g in policy.gates
        if status.get(g) not in {"pass", None} or (g in status and status[g] != "pass")
    ]
    # Gates that are absent from claims count as unmet when listed.
    for g in policy.gates:
        if g not in status and g not in metrics:
            if g not in gate_failures:
                gate_failures.append(g)

    if unmet:
        return ObjectiveResult(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            formula=policy.formula,
            component_signals=list(policy.component_signals),
            gates_satisfied=False,
            prerequisites_met=False,
            scored=False,
            unscorable=True,
            unmet_prerequisites=unmet,
            gate_failures=gate_failures,
            component_status=status,
        )

    if gate_failures:
        return ObjectiveResult(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            formula=policy.formula,
            component_signals=list(policy.component_signals),
            gates_satisfied=False,
            prerequisites_met=True,
            scored=False,
            unscorable=False,
            scalar=0.0,
            gate_failures=gate_failures,
            component_status=status,
            detail={"reason": "gate_failed"},
        )

    signals = policy.component_signals or [c.id for c in claims]
    if policy.formula == "lexicographic":
        order = policy.lexicographic or signals
        for name in order:
            if name in status and status[name] != "pass":
                return ObjectiveResult(
                    policy_id=policy.policy_id,
                    policy_version=policy.version,
                    formula=policy.formula,
                    component_signals=list(signals),
                    gates_satisfied=True,
                    prerequisites_met=True,
                    scored=True,
                    scalar=0.0,
                    component_status=status,
                    detail={"failed_signal": name},
                )
            if name in metrics:
                # First metric after all prior passes becomes the scalar.
                return ObjectiveResult(
                    policy_id=policy.policy_id,
                    policy_version=policy.version,
                    formula=policy.formula,
                    component_signals=list(signals),
                    gates_satisfied=True,
                    prerequisites_met=True,
                    scored=True,
                    scalar=float(metrics[name]),
                    component_status=status,
                    detail={"lexicographic_metric": name},
                )
        return ObjectiveResult(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            formula=policy.formula,
            component_signals=list(signals),
            gates_satisfied=True,
            prerequisites_met=True,
            scored=True,
            scalar=1.0,
            component_status=status,
        )

    if policy.formula == "gated_primary":
        primary = signals[0] if signals else None
        scalar = 1.0
        if primary and primary in metrics:
            scalar = float(metrics[primary])
        elif primary and status.get(primary) != "pass":
            scalar = 0.0
        return ObjectiveResult(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            formula=policy.formula,
            component_signals=list(signals),
            gates_satisfied=True,
            prerequisites_met=True,
            scored=True,
            scalar=scalar,
            component_status=status,
        )

    # Default: all listed component signals must pass.
    failed = [s for s in signals if status.get(s) not in (None, "pass") or status.get(s) == "fail"]
    unknown = [s for s in signals if status.get(s) == "unknown"]
    if unknown:
        return ObjectiveResult(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            formula=policy.formula,
            component_signals=list(signals),
            gates_satisfied=True,
            prerequisites_met=True,
            scored=False,
            unscorable=True,
            component_status=status,
            detail={"unknown_signals": unknown},
        )
    ok = not failed and all(status.get(s) == "pass" for s in signals if s in status)
    return ObjectiveResult(
        policy_id=policy.policy_id,
        policy_version=policy.version,
        formula=policy.formula,
        component_signals=list(signals),
        gates_satisfied=True,
        prerequisites_met=True,
        scored=True,
        scalar=1.0 if ok else 0.0,
        component_status=status,
        detail={"failed_signals": failed},
    )


def compare_lexicographic(
    policy: ObjectivePolicy,
    treatment: Mapping[str, float],
    control: Mapping[str, float],
) -> Literal["treatment", "control", "tie"]:
    """Compare two metric maps under lexicographic order (MH-MHRL-08 helper)."""
    order = policy.lexicographic or policy.component_signals
    for name in order:
        t = treatment.get(name)
        c = control.get(name)
        if t is None or c is None:
            continue
        if t > c:
            return "treatment"
        if t < c:
            return "control"
    return "tie"
