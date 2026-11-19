"""Review caller-supplied claim labels against a caller-supplied ledger.

Retrieved pages, discovered resource names, and agent memory may be recorded.
They do not create grants, drop exclusions, or revive a revoked operation.
This experimental report helper does not verify provenance or dispatch effects.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResourceOperation(BaseModel):
    """An entry in a host-supplied ledger; it is not an authorization token."""

    resource_id: str
    operation: str


class AdmissionClaim(BaseModel):
    """A source label supplied by the caller, awaiting actual source/gate validation."""

    model_config = ConfigDict(extra="allow")
    id: str
    source_class: str
    kind: str = "requirement"
    quote: str = ""
    predicate: str = ""
    uncertain: bool = False


class ProposedEffect(ResourceOperation):
    id: str


class AdmissionReport(BaseModel):
    decisions: dict[str, str] = Field(default_factory=dict)
    effects: dict[str, Literal["ledger_match", "ledger_miss"]] = Field(default_factory=dict)
    gate_status: Literal["not_evaluated"] = "not_evaluated"
    evidence_origin: Literal["caller_supplied"] = "caller_supplied"


def review_admission(
    *,
    ledger: list[dict[str, str]],
    claims: list[dict[str, Any]],
    effects: list[dict[str, str]],
) -> dict[str, Any]:
    """Report supplied claim labels and resource/operation ledger matches.

    ``ledger`` entries are ``{resource_id, operation}`` from the host authority
    store. ``claims`` carry ``id``, ``kind``, ``source_class``, ``quote``, and
    optional ``predicate``, ``resource_id``, ``operation``, ``uncertain``.
    ``effects`` are proposed calls ``{id, resource_id, operation}``.

    The host must authenticate source labels and own the trusted ledger before
    calling. A nonempty predicate is recorded, not evaluated; ``source_label_accepted`` does
    not verify the quote against a source. ``ledger_match`` means exact membership in
    the supplied ledger, not authorization by ``AuthorityGate``. The host must
    still enforce grants and revalidate authority when dispatching effects.

    Example:
        >>> review_admission(ledger=[], claims=[{
        ...     "id": "memory", "source_class": "memory",
        ...     "predicate": "restore write permission",
        ... }], effects=[{
        ...     "id": "write", "resource_id": "object:X", "operation": "write",
        ... }])["effects"]
        {'write': 'ledger_miss'}
    """
    entries = [ResourceOperation.model_validate(row) for row in ledger]
    proposed = [ProposedEffect.model_validate(row) for row in effects]
    labelled = [AdmissionClaim.model_validate(row) for row in claims]
    if len({claim.id for claim in labelled}) != len(labelled):
        raise ValueError("claim ids must be unique")
    if len({effect.id for effect in proposed}) != len(proposed):
        raise ValueError("effect ids must be unique")
    allowed = {(row.resource_id, row.operation) for row in entries}
    report = AdmissionReport(
        decisions={claim.id: _admit_claim(claim) for claim in labelled},
        effects={
            effect.id: (
                "ledger_match"
                if (effect.resource_id, effect.operation) in allowed
                else "ledger_miss"
            )
            for effect in proposed
        },
    )
    return report.model_dump(mode="json")


def _admit_claim(claim: AdmissionClaim) -> str:
    if claim.source_class != "user":
        return (
            "candidate"
            if claim.kind == "resource_candidate" or claim.source_class == "discovery"
            else "rejected"
        )
    if claim.uncertain or not claim.predicate.strip() or not claim.quote.strip():
        return "ask_human"
    return "source_label_accepted"
