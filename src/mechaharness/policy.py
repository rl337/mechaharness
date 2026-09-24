"""Pure policy verdicts over judge signals (POL-*).

``judge()`` produces observations. ``decide()`` here is deterministic authority:
models never grant permission.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.inference.judge import (
    ChoiceSignal,
    NoulSignal,
    ScoreSignal,
    Signal,
)

VerdictKind = Literal["ALLOW", "DENY", "ASK_HUMAN", "ABSTAIN"]


class PolicyThreshold(BaseModel):
    model_config = ConfigDict(extra="allow")

    signal_id: str
    # For noul: allow when p_true >= allow_above; ask human in (ask_below, allow_above)
    allow_above: float | None = None
    deny_below: float | None = None
    ask_below: float | None = None
    # For choice: allow only these selections
    allow_choices: list[str] | None = None
    deny_choices: list[str] | None = None
    # For score
    allow_min: float | None = None
    deny_max: float | None = None


class Policy(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str
    # Unknown signals → DENY (fail-closed) unless listed here as ignorable
    ignore_unknown_signals: bool = False
    thresholds: list[PolicyThreshold] = Field(default_factory=list)
    # Mutations require prior approval token matching digest
    require_approval_for: list[str] = Field(default_factory=list)


class PolicyFacts(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: str = "noop"
    action_digest: str | None = None
    approvals: Mapping[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class Verdict(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    kind: VerdictKind
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    policy_version: str = Field(alias="policyVersion")
    signals_used: list[str] = Field(default_factory=list, alias="signalsUsed")


def decide(
    facts: PolicyFacts | Mapping[str, Any],
    signals: Sequence[Signal] | Mapping[str, Signal],
    policy: Policy | Mapping[str, Any],
) -> Verdict:
    """Pure ``decide(facts, signals, policy) -> verdict`` (POL-01/02/04)."""
    pol = policy if isinstance(policy, Policy) else Policy.model_validate(policy)
    fact = facts if isinstance(facts, PolicyFacts) else PolicyFacts.model_validate(facts)
    by_id: dict[str, Signal]
    if isinstance(signals, Mapping):
        by_id = dict(signals)
    else:
        by_id = {s.id: s for s in signals}

    reasons: list[str] = []
    used: list[str] = []

    # POL-04: mutations need approval matching digest
    if fact.action in pol.require_approval_for:
        digest = fact.action_digest or ""
        token = fact.approvals.get(digest) or fact.approvals.get(fact.action)
        if not token:
            return Verdict(
                kind="ASK_HUMAN",
                reason_codes=["MISSING_APPROVAL"],
                policy_version=pol.version,
                signals_used=[],
            )

    # Fail-closed: unknown signals unless ignored
    known = {t.signal_id for t in pol.thresholds}
    for sid in by_id:
        if sid not in known and not pol.ignore_unknown_signals:
            return Verdict(
                kind="DENY",
                reason_codes=["UNKNOWN_SIGNAL", sid],
                policy_version=pol.version,
                signals_used=list(by_id),
            )

    # Deny precedence: any deny threshold fires first
    for thresh in pol.thresholds:
        signal = by_id.get(thresh.signal_id)
        if signal is None:
            reasons.append(f"MISSING_SIGNAL:{thresh.signal_id}")
            return Verdict(
                kind="DENY",
                reason_codes=reasons or ["MISSING_SIGNAL"],
                policy_version=pol.version,
                signals_used=used,
            )
        used.append(thresh.signal_id)
        kind = _evaluate_threshold(thresh, signal)
        if kind == "DENY":
            return Verdict(
                kind="DENY",
                reason_codes=[f"DENY:{thresh.signal_id}"],
                policy_version=pol.version,
                signals_used=used,
            )
        if kind == "ASK_HUMAN":
            reasons.append(f"RISK_REVIEW_BAND:{thresh.signal_id}")
        if kind == "ABSTAIN":
            reasons.append(f"ABSTAIN:{thresh.signal_id}")

    if any(r.startswith("RISK_REVIEW_BAND") for r in reasons):
        return Verdict(
            kind="ASK_HUMAN",
            reason_codes=reasons,
            policy_version=pol.version,
            signals_used=used,
        )
    if any(r.startswith("ABSTAIN") for r in reasons):
        return Verdict(
            kind="ABSTAIN",
            reason_codes=reasons,
            policy_version=pol.version,
            signals_used=used,
        )
    if any(r.startswith("MISSING_SIGNAL") for r in reasons):
        return Verdict(
            kind="DENY",
            reason_codes=reasons,
            policy_version=pol.version,
            signals_used=used,
        )
    return Verdict(
        kind="ALLOW",
        reason_codes=reasons or ["OK"],
        policy_version=pol.version,
        signals_used=used,
    )


def _evaluate_threshold(thresh: PolicyThreshold, signal: Signal) -> VerdictKind:
    if isinstance(signal, NoulSignal):
        p = signal.p_true
        if thresh.deny_below is not None and p < thresh.deny_below:
            return "DENY"
        if thresh.allow_above is not None and p >= thresh.allow_above:
            return "ALLOW"
        if thresh.ask_below is not None and p < thresh.ask_below:
            return "ASK_HUMAN"
        if thresh.allow_above is not None and p < thresh.allow_above:
            return "ASK_HUMAN"
        return "ALLOW"
    if isinstance(signal, ChoiceSignal):
        if thresh.deny_choices and signal.selected in thresh.deny_choices:
            return "DENY"
        if thresh.allow_choices is not None:
            if signal.selected in thresh.allow_choices:
                return "ALLOW"
            return "DENY"
        return "ALLOW"
    if isinstance(signal, ScoreSignal):
        if thresh.deny_max is not None and signal.value <= thresh.deny_max:
            return "DENY"
        if thresh.allow_min is not None and signal.value >= thresh.allow_min:
            return "ALLOW"
        if thresh.allow_min is not None:
            return "ASK_HUMAN"
        return "ALLOW"
    return "ABSTAIN"
