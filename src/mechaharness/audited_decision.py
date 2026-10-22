"""Audited-decision contract for generate → QA → gate (RDG-aligned).

Portable spine shared by Agentic Recipe ``audited_infer_accept`` and host
apps (e.g. FOLK's former ``ideation.infer.accept``). Stages::

    collect → freeze_criteria → decide → independent_qa → deterministic → gate
                         ↑ repair routes to the narrowest prior stage (bounded)

Modality (``text`` / ``image``) only replaces soft subgraphs under ``decide``
and ``independent_qa``. Hosts bind runners; MechaHarness owns the topology
and principal / criteria / repair rules.

Provenance: lifted from FOLK ``folk.domain.audited_decision`` for library reuse.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

Modality = Literal["text", "image"]

# Canonical stage ids — keep stable for audit bundles and host resumes.
STAGES: tuple[str, ...] = (
    "collect",
    "freeze_criteria",
    "decide",
    "independent_qa",
    "deterministic",
    "gate",
)

REPAIR_TARGETS: frozenset[str] = frozenset({"collect", "freeze_criteria", "decide"})

# Library placeholder node kinds (hosts soft-bind overrides, e.g. folk.infer.*).
DEFAULT_KIND_PREFIX = "audited"


class AuditedDecisionError(ValueError):
    """Fail-closed audited decision (criteria, authz, or gate)."""


def criteria_hash(criteria: dict[str, Any] | Sequence[str]) -> str:
    """Freeze hash for criteria (RDG-03). Order-stable."""
    if isinstance(criteria, dict):
        blob = json.dumps(criteria, sort_keys=True, ensure_ascii=False).encode()
    else:
        blob = json.dumps(list(criteria), ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()


def assert_principals_distinct(
    decide_principal: str, qa_principal: str, *, hop: str = ""
) -> None:
    """Independent QA must not be the same principal as decide (RDG-05)."""
    d = (decide_principal or "").strip()
    q = (qa_principal or "").strip()
    if not d or not q:
        raise AuditedDecisionError(
            f"{hop or 'decision'}: decide_principal and qa_principal required"
        )
    if d == q:
        raise AuditedDecisionError(
            f"{hop or 'decision'}: QA principal must differ from decide (RDG-05)"
        )


@dataclass(frozen=True)
class AuditedDecisionSpec:
    """Soft-bound input for ``audited_infer_accept``."""

    task_id: str
    modality: Modality
    """text → LM JSON decide; image → media produce + VLM QA (host-bound)."""

    acceptance_criteria: tuple[str, ...] = field(default_factory=tuple)
    """Criteria frozen before decide."""

    hop: str = ""
    """Named hop for audit."""

    decide_principal: str = "decide_agent"
    qa_principal: str = "qa_agent"
    """Must differ (RDG-05). Hosts soft-bind execution principals."""

    max_retries: int = 3
    produce_kind: str = "noop"
    """Image (or custom) produce runner kind soft-bound under decide."""

    hop_recipe: str = ""
    """Optional host leaf id (e.g. FOLK hop_accept catalog)."""

    seed_evidence: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    require_evidence_anchors: bool = True
    """When True, evidence items need anchor or passage (RDG-02)."""

    def frozen_bundle(self) -> dict[str, Any]:
        criteria = {
            "hop": self.hop,
            "modality": self.modality,
            "acceptance_criteria": list(self.acceptance_criteria),
            "nontrivial": bool(self.acceptance_criteria),
            "must_cite_evidence": self.require_evidence_anchors,
        }
        return {
            "task_id": self.task_id,
            "hop": self.hop,
            "modality": self.modality,
            "criteria": criteria,
            "criteria_hash": criteria_hash(criteria),
            "decide_principal": self.decide_principal,
            "qa_principal": self.qa_principal,
            "max_retries": self.max_retries,
            "produce_kind": self.produce_kind,
            "hop_recipe": self.hop_recipe,
        }


def repair_target(defect: str) -> str:
    """Map defect class → narrowest prior stage (RDG-07)."""
    if defect in ("missing_evidence", "unanchored_evidence"):
        return "collect"
    if defect in ("weak_criteria", "criteria_incomplete"):
        return "freeze_criteria"
    if defect in ("poor_reasoning", "accept_fail", "qa_fail", "produce_fail"):
        return "decide"
    raise AuditedDecisionError(f"unknown defect {defect!r}")


def default_stage_kinds(
    modality: Modality,
    *,
    decide_kind: str | None = None,
    qa_kind: str | None = None,
    collect_kind: str | None = None,
    freeze_kind: str | None = None,
    deterministic_kind: str | None = None,
    gate_kind: str | None = None,
    precheck_kind: str | None = None,
) -> dict[str, str]:
    """Node kinds for the spine; hosts override via soft bindings."""
    prefix = DEFAULT_KIND_PREFIX
    return {
        "precheck": precheck_kind or f"{prefix}.precheck",
        "collect": collect_kind or f"{prefix}.collect",
        "freeze_criteria": freeze_kind or f"{prefix}.freeze_criteria",
        "decide": decide_kind or f"{prefix}.{modality}.decide",
        "independent_qa": qa_kind or f"{prefix}.{modality}.qa",
        "deterministic": deterministic_kind or f"{prefix}.deterministic",
        "gate": gate_kind or f"{prefix}.gate",
    }


__all__ = [
    "DEFAULT_KIND_PREFIX",
    "AuditedDecisionError",
    "AuditedDecisionSpec",
    "Modality",
    "REPAIR_TARGETS",
    "STAGES",
    "assert_principals_distinct",
    "criteria_hash",
    "default_stage_kinds",
    "repair_target",
]
