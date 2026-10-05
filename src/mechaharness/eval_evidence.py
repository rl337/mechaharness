"""Typed evidence and binary claims for evaluation substrates.

Anthropic's *Demystifying evals for AI agents* treats graders/assertions and
transcripts as first-class eval pieces
(https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
BINEVAL pushes toward atomic binary questions instead of opaque holistic scores
(https://arxiv.org/abs/2606.27226).

MechaHarness keeps claims application-agnostic::

    >>> from mechaharness.eval_evidence import Claim, Evidence, compose_claims
    >>> evidence = Evidence(ref="event:42", kind="trace", summary="tool wrote file")
    >>> claims = [
    ...     Claim(id="wrote", statement="file exists", status="pass", evidence_refs=["event:42"]),
    ...     Claim(id="tests", statement="tests green", status="unknown"),
    ... ]
    >>> summary = compose_claims(claims)
    >>> summary["pass"]
    1
    >>> summary["unknown"]
    1
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ClaimStatus = Literal["pass", "fail", "unknown"]
EvidenceKind = Literal[
    "trace",
    "outcome",
    "oracle",
    "human",
    "model",
    "state",
    "other",
]


class Evidence(BaseModel):
    """A typed pointer to execution or outcome substrate (not stuffed into prompts)."""

    model_config = ConfigDict(extra="allow")

    ref: str
    kind: EvidenceKind = "other"
    summary: str = ""
    strength: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    """Independently resolvable binary (or unknown) assertion."""

    model_config = ConfigDict(extra="allow")

    id: str
    statement: str
    status: ClaimStatus = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)
    oracle_strength: str | None = None
    version: str = "1"
    detail: dict[str, Any] = Field(default_factory=dict)


def compose_claims(claims: list[Claim]) -> dict[str, int]:
    """Count claim statuses without collapsing into a single opaque scalar."""
    counts = {"pass": 0, "fail": 0, "unknown": 0}
    for claim in claims:
        counts[claim.status] = counts.get(claim.status, 0) + 1
    return counts


def all_passed(claims: list[Claim]) -> bool:
    return bool(claims) and all(c.status == "pass" for c in claims)
