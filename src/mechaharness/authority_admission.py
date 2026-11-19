"""Admit authority only from the trusted ledger and the user's own words.

Retrieved pages, discovered resource names, and agent memory may be recorded.
They do not create grants, drop exclusions, or revive a revoked operation.
"""

from __future__ import annotations

from typing import Any


def review_admission(
    *,
    ledger: list[dict[str, str]],
    claims: list[dict[str, Any]],
    effects: list[dict[str, str]],
) -> dict[str, Any]:
    """Return per-claim admission and per-effect allow/deny decisions.

    ``ledger`` entries are ``{resource_id, operation}`` from the host authority
    store. ``claims`` carry ``id``, ``kind``, ``source_class``, ``quote``, and
    optional ``predicate``, ``resource_id``, ``operation``, ``uncertain``.
    ``effects`` are proposed calls ``{id, resource_id, operation}``.
    """
    allowed = {
        (str(row["resource_id"]), str(row["operation"]))
        for row in ledger
    }
    decisions: dict[str, str] = {}
    for claim in claims:
        decisions[str(claim["id"])] = _admit_claim(claim)
    effect_decisions: dict[str, str] = {}
    for effect in effects:
        key = (str(effect["resource_id"]), str(effect["operation"]))
        effect_decisions[str(effect["id"])] = "allow" if key in allowed else "deny"
    return {"decisions": decisions, "effects": effect_decisions}


def _admit_claim(claim: dict[str, Any]) -> str:
    source = str(claim.get("source_class") or "")
    kind = str(claim.get("kind") or "")
    if source != "user":
        if kind == "resource_candidate" or source == "discovery":
            return "candidate"
        return "rejected"
    if claim.get("uncertain") or not str(claim.get("predicate") or "").strip():
        return "ask_human"
    return "admitted"
