"""Typed StrategyRevision helpers (gastronomic M6 strategy revision).

Deterministic retry / stop / yield gate over Diagnosis + plan + retry history.
Model text is not evidence; disposition must cite host-observed diagnosis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REVISION_VERSION = "1"

DISPOSITIONS: frozenset[str] = frozenset(
    {
        "continue_or_accept",
        "retry",
        "change_strategy",
        "stop",
        "yield_guidance",
    }
)

_DEFAULT_MAX_ATTEMPTS = 3


def extract_revision_constraints(
    *,
    diagnosis: Mapping[str, Any] | None = None,
    change_plan: Mapping[str, Any] | None = None,
    prior_attempts: Sequence[Mapping[str, Any]] | None = None,
    retry_budget: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect gate inputs from diagnosis, plan, and retry history."""
    diag = diagnosis if isinstance(diagnosis, Mapping) else {}
    plan = change_plan if isinstance(change_plan, Mapping) else {}
    attempts = [dict(row) for row in (prior_attempts or []) if isinstance(row, Mapping)]
    budget = retry_budget if isinstance(retry_budget, Mapping) else {}

    failure_class = str(diag.get("failure_class") or "")
    next_experiment = str(diag.get("next_experiment") or "").strip()
    diag_status = str(diag.get("status") or "")
    evidence = [
        dict(row) for row in (diag.get("evidence") or []) if isinstance(row, Mapping)
    ]

    provenance = diag.get("provenance")
    slice_id = None
    if isinstance(provenance, Mapping):
        slice_id = provenance.get("slice_id")
    if slice_id is None:
        slices = plan.get("slices")
        if isinstance(slices, list) and slices and isinstance(slices[0], Mapping):
            slice_id = slices[0].get("id")

    attempts_used = budget.get("attempts_used")
    if attempts_used is None:
        attempts_used = len(attempts)
    try:
        attempts_used_i = max(0, int(attempts_used))
    except (TypeError, ValueError):
        attempts_used_i = len(attempts)

    attempts_max = budget.get("attempts_max", _DEFAULT_MAX_ATTEMPTS)
    try:
        attempts_max_i = max(0, int(attempts_max))
    except (TypeError, ValueError):
        attempts_max_i = _DEFAULT_MAX_ATTEMPTS

    remaining = max(0, attempts_max_i - attempts_used_i)

    if not diag:
        status = "incomplete"
    elif diag_status == "incomplete" and failure_class in {"", "none"} and not evidence:
        status = "incomplete"
    elif diag_status == "failed":
        status = "failed"
    else:
        status = "ok"

    return {
        "status": status,
        "diagnosis_status": diag_status or None,
        "failure_class": failure_class or None,
        "next_experiment": next_experiment or None,
        "evidence": evidence,
        "prior_attempts": attempts,
        "slice_id": slice_id,
        "plan_status": str(plan.get("status") or "") or None,
        "retry_budget": {
            "attempts_used": attempts_used_i,
            "attempts_max": attempts_max_i,
            "remaining": remaining,
        },
    }


def decide_revision_gate(
    constraints: Mapping[str, Any],
    *,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministically choose disposition from revision constraints."""
    params = parameters if isinstance(parameters, Mapping) else {}
    failure_class = str(constraints.get("failure_class") or "")
    next_experiment = str(constraints.get("next_experiment") or "").strip()
    c_status = str(constraints.get("status") or "")
    budget = constraints.get("retry_budget")
    if not isinstance(budget, Mapping):
        budget = {}
    remaining = int(budget.get("remaining") or 0)
    if "attempts_max" in params:
        try:
            attempts_max = max(0, int(params["attempts_max"]))
        except (TypeError, ValueError):
            attempts_max = int(budget.get("attempts_max") or _DEFAULT_MAX_ATTEMPTS)
        attempts_used = int(budget.get("attempts_used") or 0)
        remaining = max(0, attempts_max - attempts_used)

    prior = [
        row
        for row in (constraints.get("prior_attempts") or [])
        if isinstance(row, Mapping)
    ]
    prior_experiments = {
        str(row.get("next_experiment") or "") for row in prior if row.get("next_experiment")
    }
    prior_classes = {str(row.get("failure_class") or "") for row in prior}

    if c_status == "incomplete" or not failure_class:
        return {
            "disposition": "yield_guidance",
            "next_experiment": next_experiment or "gather_more_host_evidence_before_retry",
            "reason": "diagnosis incomplete or missing failure class",
            "evidence_delta_required": True,
            "strategy_changed": False,
            "matched_rules": ["incomplete"],
        }

    if failure_class == "none":
        return {
            "disposition": "continue_or_accept",
            "next_experiment": next_experiment or "continue_or_accept",
            "reason": "no host-observed failures",
            "evidence_delta_required": False,
            "strategy_changed": False,
            "matched_rules": ["green"],
        }

    if remaining <= 0:
        return {
            "disposition": "stop",
            "next_experiment": "stop_retry_budget_exhausted",
            "reason": "retry budget exhausted",
            "evidence_delta_required": False,
            "strategy_changed": False,
            "matched_rules": ["budget_exhausted"],
        }

    if next_experiment.startswith("change_strategy_after_repeat_"):
        return {
            "disposition": "change_strategy",
            "next_experiment": next_experiment,
            "reason": "repeated failure class requires a changed strategy",
            "evidence_delta_required": True,
            "strategy_changed": True,
            "matched_rules": ["repeat_class"],
        }

    if failure_class in {"unknown", "scope"}:
        return {
            "disposition": "yield_guidance",
            "next_experiment": next_experiment
            or (
                "refuse_or_replan_within_allowed_paths"
                if failure_class == "scope"
                else "gather_more_host_evidence_before_retry"
            ),
            "reason": f"host class {failure_class} needs guidance or replan",
            "evidence_delta_required": True,
            "strategy_changed": False,
            "matched_rules": [failure_class],
        }

    if next_experiment and next_experiment in prior_experiments and failure_class in prior_classes:
        return {
            "disposition": "change_strategy",
            "next_experiment": f"change_strategy_after_repeat_{failure_class}",
            "reason": "same next_experiment already attempted for this class",
            "evidence_delta_required": True,
            "strategy_changed": True,
            "matched_rules": ["repeat_experiment"],
        }

    return {
        "disposition": "retry",
        "next_experiment": next_experiment or "gather_more_host_evidence_before_retry",
        "reason": "retry with diagnosis next_experiment under remaining budget",
        "evidence_delta_required": True,
        "strategy_changed": False,
        "matched_rules": ["retry"],
    }


def assemble_strategy_revision(
    *,
    constraints: Mapping[str, Any],
    decision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish StrategyRevision from constrain + decide receipts."""
    if decision is None:
        decision = decide_revision_gate(constraints)
    disposition = str(decision.get("disposition") or "yield_guidance")
    if disposition not in DISPOSITIONS:
        disposition = "yield_guidance"

    c_status = str(constraints.get("status") or "")
    status = "ok"
    if c_status == "incomplete" and disposition == "yield_guidance":
        status = "incomplete"
    elif c_status == "failed":
        status = "failed"

    budget = constraints.get("retry_budget")
    if not isinstance(budget, Mapping):
        budget = {
            "attempts_used": 0,
            "attempts_max": _DEFAULT_MAX_ATTEMPTS,
            "remaining": _DEFAULT_MAX_ATTEMPTS,
        }

    return {
        "version": REVISION_VERSION,
        "status": status,
        "disposition": disposition,
        "next_experiment": str(
            decision.get("next_experiment") or "gather_more_host_evidence_before_retry"
        ),
        "reason": str(decision.get("reason") or "unspecified"),
        "evidence_delta_required": bool(decision.get("evidence_delta_required")),
        "strategy_changed": bool(decision.get("strategy_changed")),
        "retry_budget": {
            "attempts_used": int(budget.get("attempts_used") or 0),
            "attempts_max": int(budget.get("attempts_max") or _DEFAULT_MAX_ATTEMPTS),
            "remaining": int(budget.get("remaining") or 0),
        },
        "prior_attempts": [
            dict(row)
            for row in (constraints.get("prior_attempts") or [])
            if isinstance(row, Mapping)
        ],
        "provenance": {
            "slice_id": constraints.get("slice_id"),
            "failure_class": constraints.get("failure_class"),
            "diagnosis_status": constraints.get("diagnosis_status"),
            "plan_status": constraints.get("plan_status"),
            "matched_rules": list(decision.get("matched_rules") or []),
        },
    }


def validate_strategy_revision(report: Mapping[str, Any]) -> dict[str, Any]:
    """Schema report for a StrategyRevision (non-raising)."""
    errors: list[dict[str, str]] = []
    if str(report.get("version") or "") != REVISION_VERSION:
        errors.append({"path": "version", "message": f"expected {REVISION_VERSION}"})
    status = str(report.get("status") or "")
    if status not in {"ok", "incomplete", "failed"}:
        errors.append({"path": "status", "message": "ok|incomplete|failed required"})
    disposition = str(report.get("disposition") or "")
    if disposition not in DISPOSITIONS:
        errors.append(
            {
                "path": "disposition",
                "message": "|".join(sorted(DISPOSITIONS)) + " required",
            }
        )
    if not str(report.get("next_experiment") or "").strip():
        errors.append({"path": "next_experiment", "message": "nonempty required"})
    if not str(report.get("reason") or "").strip():
        errors.append({"path": "reason", "message": "nonempty required"})
    if "evidence_delta_required" not in report:
        errors.append({"path": "evidence_delta_required", "message": "bool required"})
    if "strategy_changed" not in report:
        errors.append({"path": "strategy_changed", "message": "bool required"})
    budget = report.get("retry_budget")
    if not isinstance(budget, Mapping):
        errors.append({"path": "retry_budget", "message": "object required"})
    else:
        for key in ("attempts_used", "attempts_max", "remaining"):
            raw = budget.get(key)
            try:
                if raw is None:
                    raise TypeError("missing")
                int(raw)
            except (TypeError, ValueError):
                errors.append({"path": f"retry_budget.{key}", "message": "int required"})
    if not isinstance(report.get("prior_attempts"), list):
        errors.append({"path": "prior_attempts", "message": "list required"})
    if disposition == "retry" and not report.get("evidence_delta_required"):
        errors.append(
            {
                "path": "evidence_delta_required",
                "message": "must be true when disposition is retry",
            }
        )
    if disposition == "change_strategy" and not report.get("strategy_changed"):
        errors.append(
            {
                "path": "strategy_changed",
                "message": "must be true when disposition is change_strategy",
            }
        )
    return {"ok": not errors, "errors": errors}


__all__ = [
    "DISPOSITIONS",
    "REVISION_VERSION",
    "assemble_strategy_revision",
    "decide_revision_gate",
    "extract_revision_constraints",
    "validate_strategy_revision",
]
