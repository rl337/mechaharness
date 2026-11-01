"""Typed DevelopmentOutcome helpers (gastronomic M6 development acceptance).

Deterministic acceptance gates over contract, verification, execution, and
strategy revision. Model/judge text is advisory only — never host evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

OUTCOME_VERSION = "1"

OUTCOMES: frozenset[str] = frozenset(
    {
        "completed",
        "needs_guidance",
        "failed",
    }
)


def extract_acceptance_constraints(
    *,
    change_contract: Mapping[str, Any] | None = None,
    verification_report: Mapping[str, Any] | None = None,
    change_execution: Mapping[str, Any] | None = None,
    strategy_revision: Mapping[str, Any] | None = None,
    coverage: Mapping[str, Any] | None = None,
    judge_opinion: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect gate inputs from stage receipts (plus optional advisory judge)."""
    contract = change_contract if isinstance(change_contract, Mapping) else {}
    verify = verification_report if isinstance(verification_report, Mapping) else {}
    execution = change_execution if isinstance(change_execution, Mapping) else {}
    revision = strategy_revision if isinstance(strategy_revision, Mapping) else {}
    cov = coverage if isinstance(coverage, Mapping) else {}
    judge = judge_opinion if isinstance(judge_opinion, Mapping) else {}

    evidence: list[dict[str, Any]] = []
    for item in verify.get("failures") or []:
        text = str(item).strip()
        if text:
            evidence.append({"source": "verification.failures", "text": text})
    regression = verify.get("regression")
    if isinstance(regression, Mapping) and not regression.get(
        "unchanged_invariants_ok", True
    ):
        evidence.append(
            {
                "source": "verification.regression",
                "text": "unchanged_invariants_ok is false",
            }
        )
    for item in execution.get("scope_violations") or []:
        text = (
            str(item).strip()
            if not isinstance(item, Mapping)
            else str(item.get("reason") or item.get("path") or item)
        )
        if text:
            evidence.append({"source": "execution.scope_violations", "text": text})
    for item in execution.get("refused") or []:
        if isinstance(item, Mapping):
            text = str(item.get("reason") or item.get("path") or item)
        else:
            text = str(item).strip()
        if text:
            evidence.append({"source": "execution.refused", "text": text})

    gates = {
        "contract_ok": str(contract.get("status") or "") in {"", "ok"},
        "verification_ok": str(verify.get("status") or "") == "ok",
        "regression_ok": True,
        "execution_ok": str(execution.get("status") or "") in {"", "ok"},
        "scope_ok": not bool(execution.get("scope_violations") or execution.get("refused")),
        "revision_accept": False,
        "coverage_ok": True,
    }
    if isinstance(regression, Mapping):
        gates["regression_ok"] = bool(regression.get("unchanged_invariants_ok", True))
    disposition = str(revision.get("disposition") or "")
    if disposition == "continue_or_accept":
        gates["revision_accept"] = True
    elif not revision and gates["verification_ok"] and gates["regression_ok"]:
        # Green verify without an explicit revision still may accept.
        gates["revision_accept"] = True

    if cov:
        try:
            observed = float(cov.get("observed", cov.get("ratio", 0.0)))
            required = float(cov.get("required", cov.get("min_ratio", 0.0)))
            gates["coverage_ok"] = observed >= required
        except (TypeError, ValueError):
            gates["coverage_ok"] = False
            evidence.append(
                {
                    "source": "coverage",
                    "text": "coverage values are not numeric",
                }
            )
        else:
            if not gates["coverage_ok"]:
                evidence.append(
                    {
                        "source": "coverage",
                        "text": f"observed {observed} < required {required}",
                    }
                )

    present = any([contract, verify, execution, revision])
    if not present:
        status = "incomplete"
    elif str(verify.get("status") or "") == "incomplete" and not evidence:
        status = "incomplete"
    elif str(verify.get("status") or "") == "failed" or str(execution.get("status") or "") == "failed":
        status = "failed"
    else:
        status = "ok"

    provenance = verify.get("provenance") if isinstance(verify.get("provenance"), Mapping) else {}
    slice_id = provenance.get("slice_id") if isinstance(provenance, Mapping) else None
    if slice_id is None:
        slice_id = execution.get("slice_id")

    return {
        "status": status,
        "contract_status": str(contract.get("status") or "") or None,
        "verification_status": str(verify.get("status") or "") or None,
        "execution_status": str(execution.get("status") or "") or None,
        "revision_disposition": disposition or None,
        "gates": gates,
        "evidence": evidence,
        "coverage": dict(cov) if cov else None,
        "judge_opinion": dict(judge) if judge else None,
        "slice_id": slice_id,
        "changed_files": [
            dict(row)
            for row in (execution.get("changed_files") or [])
            if isinstance(row, Mapping)
        ],
    }


def decide_acceptance_outcome(
    constraints: Mapping[str, Any],
    *,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministically map gates to completed | needs_guidance | failed."""
    del parameters  # reserved for host thresholds; gates already applied
    gates = constraints.get("gates")
    if not isinstance(gates, Mapping):
        gates = {}
    c_status = str(constraints.get("status") or "")
    disposition = str(constraints.get("revision_disposition") or "")
    evidence = [
        row for row in (constraints.get("evidence") or []) if isinstance(row, Mapping)
    ]

    if c_status == "incomplete" or not gates:
        return {
            "outcome": "needs_guidance",
            "reason": "acceptance inputs incomplete",
            "matched_rules": ["incomplete"],
            "gates_passed": False,
        }

    all_green = all(
        bool(gates.get(key))
        for key in (
            "contract_ok",
            "verification_ok",
            "regression_ok",
            "execution_ok",
            "scope_ok",
            "revision_accept",
            "coverage_ok",
        )
    )
    if all_green and not evidence:
        return {
            "outcome": "completed",
            "reason": "host gates passed with no residual failures",
            "matched_rules": ["all_green"],
            "gates_passed": True,
        }

    if disposition == "yield_guidance":
        return {
            "outcome": "needs_guidance",
            "reason": "strategy revision yielded guidance",
            "matched_rules": ["yield_guidance"],
            "gates_passed": False,
        }

    if disposition in {"retry", "change_strategy"}:
        return {
            "outcome": "needs_guidance",
            "reason": f"revision still open ({disposition})",
            "matched_rules": [disposition],
            "gates_passed": False,
        }

    if disposition == "stop" or c_status == "failed" or not gates.get("scope_ok", True):
        return {
            "outcome": "failed",
            "reason": "host gates failed or retry budget stopped",
            "matched_rules": ["failed_or_stopped"],
            "gates_passed": False,
        }

    if not gates.get("verification_ok", False) or not gates.get("regression_ok", False):
        return {
            "outcome": "failed",
            "reason": "verification or regression gate failed",
            "matched_rules": ["verify_failed"],
            "gates_passed": False,
        }

    if not gates.get("coverage_ok", True):
        return {
            "outcome": "failed",
            "reason": "coverage gate failed",
            "matched_rules": ["coverage_failed"],
            "gates_passed": False,
        }

    return {
        "outcome": "needs_guidance",
        "reason": "acceptance undecided; escalate for host review",
        "matched_rules": ["undecided"],
        "gates_passed": False,
    }


def assemble_development_outcome(
    *,
    constraints: Mapping[str, Any],
    decision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish DevelopmentOutcome from constrain + decide receipts."""
    if decision is None:
        decision = decide_acceptance_outcome(constraints)
    outcome = str(decision.get("outcome") or "needs_guidance")
    if outcome not in OUTCOMES:
        outcome = "needs_guidance"

    c_status = str(constraints.get("status") or "")
    status = "ok"
    if c_status == "incomplete" and outcome == "needs_guidance":
        status = "incomplete"
    elif c_status == "failed" or outcome == "failed":
        status = "failed"

    gates = constraints.get("gates")
    if not isinstance(gates, Mapping):
        gates = {}

    judge = constraints.get("judge_opinion")
    # Advisory only — never upgrades a failed host gate to completed.
    if (
        isinstance(judge, Mapping)
        and outcome != "completed"
        and str(judge.get("verdict") or "").lower() in {"pass", "accept", "completed"}
    ):
        # Keep host outcome; record advisory note in provenance only.
        pass

    return {
        "version": OUTCOME_VERSION,
        "status": status,
        "outcome": outcome,
        "reason": str(decision.get("reason") or "unspecified"),
        "gates": dict(gates),
        "evidence": [
            dict(row)
            for row in (constraints.get("evidence") or [])
            if isinstance(row, Mapping)
        ],
        "provenance": {
            "slice_id": constraints.get("slice_id"),
            "contract_status": constraints.get("contract_status"),
            "verification_status": constraints.get("verification_status"),
            "execution_status": constraints.get("execution_status"),
            "revision_disposition": constraints.get("revision_disposition"),
            "matched_rules": list(decision.get("matched_rules") or []),
            "gates_passed": bool(decision.get("gates_passed")),
            "changed_file_count": len(
                [
                    row
                    for row in (constraints.get("changed_files") or [])
                    if isinstance(row, Mapping)
                ]
            ),
            "judge_opinion": (
                dict(judge) if isinstance(judge, Mapping) else None
            ),
            "coverage": constraints.get("coverage"),
        },
    }


def validate_development_outcome(report: Mapping[str, Any]) -> dict[str, Any]:
    """Schema report for a DevelopmentOutcome (non-raising)."""
    errors: list[dict[str, str]] = []
    if str(report.get("version") or "") != OUTCOME_VERSION:
        errors.append({"path": "version", "message": f"expected {OUTCOME_VERSION}"})
    status = str(report.get("status") or "")
    if status not in {"ok", "incomplete", "failed"}:
        errors.append({"path": "status", "message": "ok|incomplete|failed required"})
    outcome = str(report.get("outcome") or "")
    if outcome not in OUTCOMES:
        errors.append(
            {
                "path": "outcome",
                "message": "|".join(sorted(OUTCOMES)) + " required",
            }
        )
    if not str(report.get("reason") or "").strip():
        errors.append({"path": "reason", "message": "nonempty required"})
    if not isinstance(report.get("gates"), Mapping):
        errors.append({"path": "gates", "message": "object required"})
    if not isinstance(report.get("evidence"), list):
        errors.append({"path": "evidence", "message": "list required"})
    if outcome == "completed" and report.get("evidence"):
        errors.append(
            {
                "path": "outcome",
                "message": "must not be completed when residual evidence is present",
            }
        )
    if outcome == "completed" and status != "ok":
        errors.append(
            {
                "path": "status",
                "message": "must be ok when outcome is completed",
            }
        )
    return {"ok": not errors, "errors": errors}


__all__ = [
    "OUTCOMES",
    "OUTCOME_VERSION",
    "assemble_development_outcome",
    "decide_acceptance_outcome",
    "extract_acceptance_constraints",
    "validate_development_outcome",
]
