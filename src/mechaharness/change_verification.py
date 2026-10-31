"""Typed VerificationReport helpers (gastronomic M6 change verification).

Host-observed checks against a ChangeExecution + ChangeContract. Model text is
not evidence; file hashes and verify_runs are.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

VERIFICATION_REPORT_VERSION = "1"


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)]


def _norm_rel(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def extract_verification_constraints(
    *,
    change_contract: Mapping[str, Any] | None = None,
    change_execution: Mapping[str, Any] | None = None,
    verify_runs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge contract/slice verification specs and execution provenance."""
    contract = change_contract if isinstance(change_contract, Mapping) else {}
    execution = change_execution if isinstance(change_execution, Mapping) else {}
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(row: Mapping[str, Any]) -> None:
        key = repr(sorted((str(k), repr(v)) for k, v in row.items()))
        if key in seen:
            return
        seen.add(key)
        specs.append(dict(row))

    for row in verify_runs or []:
        if isinstance(row, Mapping):
            _add(row)
    for row in contract.get("verification") or []:
        if isinstance(row, Mapping):
            _add(row)
    for row in contract.get("invariants") or []:
        if not isinstance(row, Mapping):
            continue
        check = row.get("check")
        if isinstance(check, Mapping):
            _add(check)

    changed = {
        _norm_rel(str(row.get("path") or ""))
        for row in (execution.get("changed_files") or [])
        if isinstance(row, Mapping) and row.get("path")
    }
    immutable: list[dict[str, Any]] = []
    for row in contract.get("invariants") or []:
        if not isinstance(row, Mapping) or not row.get("immutable"):
            continue
        path = _norm_rel(str(row.get("path") or ""))
        if not path:
            continue
        immutable.append(
            {
                "id": str(row.get("id") or f"preserve:{path}"),
                "path": path,
                "sha256": row.get("sha256"),
                "changed": path in changed,
            }
        )

    status = "ok"
    if str(execution.get("status") or "") == "failed":
        status = "failed"
    elif str(execution.get("status") or "") == "incomplete" or not specs:
        # Specs can still be empty when only hash invariants are checked.
        status = "ok" if immutable else "incomplete"
    if str(contract.get("status") or "") == "failed":
        status = "failed"
    elif str(contract.get("status") or "") == "incomplete" and status == "ok":
        status = "incomplete"

    return {
        "status": status,
        "verify_runs": specs,
        "immutable_invariants": immutable,
        "slice_id": str(execution.get("slice_id") or ""),
        "diff_present": bool(str(execution.get("diff") or "").strip()),
        "changed_paths": sorted(changed),
    }


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def run_host_verify_runs(
    *,
    root: Path,
    specs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Execute verify_runs specs; return per-run result dicts (host-observed)."""
    results: list[dict[str, Any]] = []
    workspace = Path(root)
    for index, spec in enumerate(specs):
        if not isinstance(spec, Mapping):
            results.append(
                {
                    "index": index,
                    "ok": False,
                    "failures": [f"verify_runs[{index}]: object required"],
                }
            )
            continue
        path = str(spec.get("path") or "").strip()
        use_pytest = bool(spec.get("pytest"))
        failures: list[str] = []
        target = workspace / path if path else workspace
        text_needles = _as_str_list(spec.get("text_contains"))
        text_forbids = _as_str_list(spec.get("text_forbids"))
        python_parses = bool(spec.get("python_parses"))
        needs_body = bool(text_needles or text_forbids or python_parses)
        if needs_body:
            if not target.is_file():
                failures.append(f"verify_runs[{index}]: missing file {path}")
            else:
                try:
                    body = target.read_text(encoding="utf-8")
                except OSError as exc:
                    failures.append(f"verify_runs[{index}] {path}: read failed: {exc}")
                    body = ""
                else:
                    if python_parses:
                        try:
                            ast.parse(body, filename=path)
                        except SyntaxError as exc:
                            failures.append(
                                f"verify_runs[{index}] {path}: python_parses failed: {exc}"
                            )
                    for needle in text_needles:
                        if needle not in body:
                            failures.append(
                                f"verify_runs[{index}] {path}: expected file text "
                                f"to contain {needle!r}"
                            )
                    for banned in text_forbids:
                        if banned in body:
                            failures.append(
                                f"verify_runs[{index}] {path}: file text must not "
                                f"contain {banned!r}"
                            )
        if use_pytest:
            if path and not target.exists():
                failures.append(f"verify_runs[{index}]: missing pytest path {path}")
            else:
                cmd = [sys.executable, "-m", "pytest", "-q"]
                if path:
                    cmd.append(path)
                cmd.extend(str(a) for a in list(spec.get("args") or []))
                expected_exit = int(spec.get("exit_code", 0))
                try:
                    completed = subprocess.run(
                        cmd,
                        cwd=str(workspace),
                        capture_output=True,
                        text=True,
                        timeout=float(spec.get("timeout_seconds") or 60.0),
                        check=False,
                    )
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"verify_runs[{index}] pytest {path}: {exc}")
                else:
                    if int(completed.returncode) != expected_exit:
                        failures.append(
                            f"verify_runs[{index}] pytest {path}: exit "
                            f"{completed.returncode} != {expected_exit}; "
                            f"stdout={completed.stdout.strip()!r}; "
                            f"stderr={completed.stderr.strip()!r}"
                        )
        results.append(
            {
                "index": index,
                "path": path,
                "ok": not failures,
                "failures": failures,
                "spec": dict(spec),
            }
        )
    return results


def check_immutable_invariants(
    *,
    root: Path,
    invariants: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Ensure untouched immutable path+hash invariants still match on disk."""
    failures: list[str] = []
    checked = 0
    for row in invariants:
        if not isinstance(row, Mapping):
            continue
        if row.get("changed"):
            continue
        path = _norm_rel(str(row.get("path") or ""))
        expected = row.get("sha256")
        if not path or not expected:
            continue
        checked += 1
        current = _file_sha256(Path(root) / path)
        if current is None:
            failures.append(f"invariant {row.get('id')}: missing file {path}")
        elif str(current) != str(expected):
            failures.append(f"invariant {row.get('id')}: sha256 changed for untouched {path}")
    return {
        "ok": not failures,
        "checked": checked,
        "failures": failures,
    }


def assemble_verification_report(
    *,
    constraints: Mapping[str, Any],
    run_results: Sequence[Mapping[str, Any]] | None = None,
    invariant_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish VerificationReport from constrain + host run receipts."""
    results = [dict(row) for row in (run_results or []) if isinstance(row, Mapping)]
    inv = invariant_report if isinstance(invariant_report, Mapping) else {}
    failures: list[str] = []
    for row in results:
        failures.extend(str(item) for item in (row.get("failures") or []))
    failures.extend(str(item) for item in (inv.get("failures") or []))

    status = "ok"
    c_status = str(constraints.get("status") or "")
    if c_status == "failed" or failures:
        status = "failed"
    elif c_status == "incomplete":
        status = "incomplete"
    elif not results and not inv.get("checked"):
        status = "incomplete"

    return {
        "version": VERIFICATION_REPORT_VERSION,
        "status": status,
        "verify_runs": results,
        "failures": failures,
        "regression": {
            "unchanged_invariants_ok": bool(inv.get("ok", True)),
            "invariants_checked": int(inv.get("checked") or 0),
        },
        "provenance": {
            "slice_id": constraints.get("slice_id"),
            "diff_present": bool(constraints.get("diff_present")),
            "changed_paths": list(constraints.get("changed_paths") or []),
            "run_count": len(results),
        },
    }


def validate_verification_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Schema report for a VerificationReport (non-raising)."""
    errors: list[dict[str, str]] = []
    if str(report.get("version") or "") != VERIFICATION_REPORT_VERSION:
        errors.append(
            {
                "path": "version",
                "message": f"expected {VERIFICATION_REPORT_VERSION}",
            }
        )
    status = str(report.get("status") or "")
    if status not in {"ok", "incomplete", "failed"}:
        errors.append({"path": "status", "message": "ok|incomplete|failed required"})
    if not isinstance(report.get("verify_runs"), list):
        errors.append({"path": "verify_runs", "message": "list required"})
    if not isinstance(report.get("failures"), list):
        errors.append({"path": "failures", "message": "list required"})
    if not isinstance(report.get("regression"), Mapping):
        errors.append({"path": "regression", "message": "object required"})
    if status == "ok":
        if report.get("failures"):
            errors.append({"path": "failures", "message": "must be empty when ok"})
        regression = report.get("regression")
        if isinstance(regression, Mapping) and not regression.get("unchanged_invariants_ok", True):
            errors.append(
                {
                    "path": "regression.unchanged_invariants_ok",
                    "message": "must be true when ok",
                }
            )
    return {"ok": not errors, "errors": errors}


__all__ = [
    "VERIFICATION_REPORT_VERSION",
    "assemble_verification_report",
    "check_immutable_invariants",
    "extract_verification_constraints",
    "run_host_verify_runs",
    "validate_verification_report",
]
