"""Typed Diagnosis helpers (gastronomic M6 failure diagnosis).

Host-observed classification of VerificationReport failures. Model text is not
evidence; failure strings and prior-attempt records are.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

DIAGNOSIS_VERSION = "1"

FAILURE_CLASSES: frozenset[str] = frozenset(
    {
        "none",
        "syntax",
        "tool_protocol",
        "runtime",
        "semantics",
        "regression",
        "budget",
        "scope",
        "unknown",
    }
)

_NEXT_EXPERIMENT: dict[str, str] = {
    "none": "continue_or_accept",
    "syntax": "fix_parse_error_at_cited_span",
    "tool_protocol": "repair_tool_call_shape_or_schema",
    "runtime": "fix_exception_at_cited_frame",
    "semantics": "adjust_behavior_to_satisfy_failing_check",
    "regression": "restore_untouched_invariant_or_narrow_scope",
    "budget": "raise_budget_or_narrow_work",
    "scope": "refuse_or_replan_within_allowed_paths",
    "unknown": "gather_more_host_evidence_before_retry",
}


def extract_diagnosis_constraints(
    *,
    verification_report: Mapping[str, Any] | None = None,
    change_execution: Mapping[str, Any] | None = None,
    prior_attempts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Collect evidence rows for classification from verify/execution receipts."""
    report = verification_report if isinstance(verification_report, Mapping) else {}
    execution = change_execution if isinstance(change_execution, Mapping) else {}
    attempts = [dict(row) for row in (prior_attempts or []) if isinstance(row, Mapping)]

    evidence: list[dict[str, Any]] = []
    for item in report.get("failures") or []:
        text = str(item).strip()
        if text:
            evidence.append({"source": "verification.failures", "text": text})
    for row in report.get("verify_runs") or []:
        if not isinstance(row, Mapping) or row.get("ok", True):
            continue
        for item in row.get("failures") or []:
            text = str(item).strip()
            if text:
                evidence.append(
                    {
                        "source": "verification.verify_runs",
                        "text": text,
                        "path": row.get("path"),
                        "index": row.get("index"),
                    }
                )
    regression = report.get("regression")
    if isinstance(regression, Mapping) and not regression.get("unchanged_invariants_ok", True):
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

    v_status = str(report.get("status") or "")
    e_status = str(execution.get("status") or "")
    if evidence:
        status = "ok"
    elif v_status == "ok" and e_status in {"", "ok"}:
        status = "ok"
    elif not report and not execution:
        status = "incomplete"
    else:
        status = "incomplete"

    provenance = report.get("provenance")
    slice_id = (
        provenance.get("slice_id") if isinstance(provenance, Mapping) else None
    ) or execution.get("slice_id")

    return {
        "status": status,
        "verification_status": v_status or None,
        "execution_status": e_status or None,
        "evidence": evidence,
        "prior_attempts": attempts,
        "slice_id": slice_id,
    }


def classify_failure_evidence(
    evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Deterministically map evidence texts to a failure class + cause."""
    texts = [str(row.get("text") or "") for row in evidence if isinstance(row, Mapping)]
    joined = "\n".join(texts).lower()
    if not texts:
        return {
            "failure_class": "none",
            "suspected_cause": "no host-observed failures",
            "confidence": 1.0,
            "matched_rules": [],
        }

    rules: list[tuple[str, re.Pattern[str], str, float]] = [
        (
            "regression",
            re.compile(r"sha256|invariant|unchanged_invariants"),
            "untouched invariant or hash diverged",
            0.95,
        ),
        (
            "scope",
            re.compile(r"scope_escape|outside allowed|refused"),
            "write escaped approved slice scope",
            0.95,
        ),
        (
            "syntax",
            re.compile(r"syntaxerror|python_parses|invalid syntax"),
            "source failed to parse",
            0.9,
        ),
        (
            "tool_protocol",
            re.compile(r"tool_call|tool protocol|malformed.*json|function.?call"),
            "malformed tool or protocol payload",
            0.85,
        ),
        (
            "budget",
            re.compile(r"timeout|budget|max_tokens|exhausted|token limit"),
            "budget or timeout exhausted",
            0.85,
        ),
        (
            "runtime",
            re.compile(
                r"importerror|modulenotfound|nameerror|attributeerror|"
                r"filenotfound|traceback|exception:"
            ),
            "runtime exception while executing checks",
            0.8,
        ),
        (
            "semantics",
            re.compile(
                r"assertionerror|pytest|exit \d+|text_contains|expected|"
                r"must not contain|failed:"
            ),
            "check assertion or expected behavior failed",
            0.75,
        ),
    ]
    matched: list[str] = []
    for name, pattern, cause, confidence in rules:
        if pattern.search(joined):
            matched.append(name)
            return {
                "failure_class": name,
                "suspected_cause": cause,
                "confidence": confidence,
                "matched_rules": matched,
            }
    return {
        "failure_class": "unknown",
        "suspected_cause": "unclassified host failure evidence",
        "confidence": 0.4,
        "matched_rules": matched,
    }


def assemble_diagnosis(
    *,
    constraints: Mapping[str, Any],
    classification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish Diagnosis from constrain + classify receipts."""
    evidence = [
        dict(row) for row in (constraints.get("evidence") or []) if isinstance(row, Mapping)
    ]
    prior = [
        dict(row) for row in (constraints.get("prior_attempts") or []) if isinstance(row, Mapping)
    ]
    if classification is None:
        classification = classify_failure_evidence(evidence)
    failure_class = str(classification.get("failure_class") or "unknown")
    if failure_class not in FAILURE_CLASSES:
        failure_class = "unknown"

    c_status = str(constraints.get("status") or "")
    status = "ok"
    if c_status == "incomplete" and failure_class == "none" and not evidence:
        status = "incomplete"
    elif c_status == "failed":
        status = "failed"

    next_experiment = _NEXT_EXPERIMENT.get(failure_class, _NEXT_EXPERIMENT["unknown"])
    # Distinct experiment when the same class was already attempted.
    attempted_classes = {
        str(row.get("failure_class") or "") for row in prior if isinstance(row, Mapping)
    }
    if failure_class in attempted_classes and failure_class not in {"none", "unknown"}:
        next_experiment = f"change_strategy_after_repeat_{failure_class}"

    return {
        "version": DIAGNOSIS_VERSION,
        "status": status,
        "failure_class": failure_class,
        "evidence": evidence,
        "suspected_cause": str(classification.get("suspected_cause") or "unspecified"),
        "next_experiment": next_experiment,
        "confidence": float(classification.get("confidence") or 0.0),
        "prior_attempts": prior,
        "provenance": {
            "slice_id": constraints.get("slice_id"),
            "verification_status": constraints.get("verification_status"),
            "execution_status": constraints.get("execution_status"),
            "matched_rules": list(classification.get("matched_rules") or []),
            "evidence_count": len(evidence),
        },
    }


def validate_diagnosis(report: Mapping[str, Any]) -> dict[str, Any]:
    """Schema report for a Diagnosis (non-raising)."""
    errors: list[dict[str, str]] = []
    if str(report.get("version") or "") != DIAGNOSIS_VERSION:
        errors.append({"path": "version", "message": f"expected {DIAGNOSIS_VERSION}"})
    status = str(report.get("status") or "")
    if status not in {"ok", "incomplete", "failed"}:
        errors.append({"path": "status", "message": "ok|incomplete|failed required"})
    failure_class = str(report.get("failure_class") or "")
    if failure_class not in FAILURE_CLASSES:
        errors.append(
            {
                "path": "failure_class",
                "message": "|".join(sorted(FAILURE_CLASSES)) + " required",
            }
        )
    if not isinstance(report.get("evidence"), list):
        errors.append({"path": "evidence", "message": "list required"})
    if not str(report.get("suspected_cause") or "").strip():
        errors.append({"path": "suspected_cause", "message": "nonempty required"})
    if not str(report.get("next_experiment") or "").strip():
        errors.append({"path": "next_experiment", "message": "nonempty required"})
    try:
        conf = float(report.get("confidence"))
    except (TypeError, ValueError):
        errors.append({"path": "confidence", "message": "number required"})
    else:
        if conf < 0.0 or conf > 1.0:
            errors.append({"path": "confidence", "message": "must be in [0,1]"})
    if not isinstance(report.get("prior_attempts"), list):
        errors.append({"path": "prior_attempts", "message": "list required"})
    if failure_class == "none" and report.get("evidence"):
        errors.append(
            {
                "path": "failure_class",
                "message": "must not be none when evidence is present",
            }
        )
    return {"ok": not errors, "errors": errors}


__all__ = [
    "DIAGNOSIS_VERSION",
    "FAILURE_CLASSES",
    "assemble_diagnosis",
    "classify_failure_evidence",
    "extract_diagnosis_constraints",
    "validate_diagnosis",
]
