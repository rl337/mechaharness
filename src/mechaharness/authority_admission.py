"""Review caller-supplied claim labels against a caller-supplied ledger.

Retrieved pages, discovered resource names, and agent memory may be recorded.
They do not create grants, drop exclusions, or revive a revoked operation.
This experimental report helper does not verify provenance or dispatch effects.
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

    The host must authenticate source labels and own the trusted ledger before
    calling. A nonempty predicate is recorded, not evaluated; ``admitted`` does
    not verify the quote against a source. ``allow`` means exact membership in
    the supplied ledger, not authorization by ``AuthorityGate``. The host must
    still enforce grants and revalidate authority when dispatching effects.

    Example:
        >>> review_admission(ledger=[], claims=[{
        ...     "id": "memory", "source_class": "memory",
        ...     "predicate": "restore write permission",
        ... }], effects=[{
        ...     "id": "write", "resource_id": "object:X", "operation": "write",
        ... }])
        {'decisions': {'memory': 'rejected'}, 'effects': {'write': 'deny'}}
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
