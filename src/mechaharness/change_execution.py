"""Typed ChangeExecution helpers (gastronomic M6 change execution).

Applies one approved ChangePlan slice with explicit write grants and scope
confinement, then publishes real diffs and before/after file hashes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from difflib import unified_diff
from pathlib import Path
from typing import Any

from pyiv.files import Filesystem

from mechaharness.project_coding_tools import WorkspacePaths

CHANGE_EXECUTION_VERSION = "1"
WRITE_GRANT = "core:fs.write"


def _norm_rel(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def extract_execution_constraints(
    *,
    approved_slice: Mapping[str, Any] | None,
    change_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the approved slice and its allowed write paths."""
    selected = approved_slice if isinstance(approved_slice, Mapping) else None
    plan = change_plan if isinstance(change_plan, Mapping) else {}
    if selected is None:
        for row in plan.get("slices") or []:
            if isinstance(row, Mapping):
                selected = row
                break
    if selected is None:
        return {
            "status": "incomplete",
            "slice_id": "",
            "allowed_paths": [],
            "write_grants_required": [WRITE_GRANT],
            "errors": [{"path": "approved_slice", "message": "required"}],
        }

    scope_raw = selected.get("scope")
    scope: Mapping[str, Any] = scope_raw if isinstance(scope_raw, Mapping) else {}
    allowed: list[str] = []
    for path in scope.get("paths") or []:
        rel = _norm_rel(str(path))
        if rel:
            allowed.append(rel)
    status = "ok" if allowed else "incomplete"
    errors: list[dict[str, str]] = []
    if not allowed:
        errors.append(
            {"path": "scope.paths", "message": "at least one allowed path required"}
        )
    return {
        "status": status,
        "slice_id": str(selected.get("id") or ""),
        "title": str(selected.get("title") or ""),
        "allowed_paths": allowed,
        "write_grants_required": [WRITE_GRANT],
        "checks": list(selected.get("checks") or []),
        "rollback": str(selected.get("rollback") or ""),
        "errors": errors,
    }


def _file_digest(fs: Filesystem, path: str) -> str | None:
    if not fs.exists(path) or not fs.is_file(path):
        return None
    return hashlib.sha256(fs.read_bytes(path)).hexdigest()


def _unified_text_diff(*, path: str, before: str, after: str) -> str:
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def apply_file_revisions(
    *,
    fs: Filesystem,
    root: Path,
    revisions: Sequence[Mapping[str, Any]],
    allowed_paths: Sequence[str],
) -> dict[str, Any]:
    """Write declared revisions under workspace+scope; refuse escapes."""
    paths = WorkspacePaths(root)
    allow = {_norm_rel(p) for p in allowed_paths}
    written: list[dict[str, Any]] = []
    refused: list[dict[str, str]] = []
    for row in revisions:
        if not isinstance(row, Mapping):
            continue
        rel = _norm_rel(str(row.get("path") or ""))
        if not rel:
            refused.append({"path": "", "reason": "missing_path"})
            continue
        if rel not in allow:
            refused.append({"path": rel, "reason": "scope_escape"})
            continue
        content = row.get("content")
        if not isinstance(content, str):
            refused.append({"path": rel, "reason": "content_must_be_string"})
            continue
        try:
            target = paths.resolve(rel)
        except ValueError:
            refused.append({"path": rel, "reason": "workspace_escape"})
            continue
        target_s = str(target)
        before_hash = _file_digest(fs, target_s)
        before_text = ""
        if before_hash is not None:
            before_text = fs.read_text(target_s)
        parent = str(target.parent)
        if not fs.exists(parent):
            fs.mkdir(parent, parents=True)
        fs.write_text(target_s, content)
        after_hash = _file_digest(fs, target_s) or ""
        written.append(
            {
                "path": rel,
                "sha256_before": before_hash,
                "sha256_after": after_hash,
                "diff": _unified_text_diff(path=rel, before=before_text, after=content),
            }
        )
    status = "ok"
    if refused and not written:
        status = "failed"
    elif refused:
        status = "failed"
    elif not written:
        status = "incomplete"
    return {
        "status": status,
        "written": written,
        "refused": refused,
    }


def assemble_change_execution(
    *,
    constraints: Mapping[str, Any],
    apply_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish ChangeExecution from constrain + apply receipts."""
    receipt = apply_receipt if isinstance(apply_receipt, Mapping) else {}
    written = [
        dict(row)
        for row in (receipt.get("written") or [])
        if isinstance(row, Mapping)
    ]
    refused = [
        dict(row)
        for row in (receipt.get("refused") or [])
        if isinstance(row, Mapping)
    ]
    status = "ok"
    c_status = str(constraints.get("status") or "")
    a_status = str(receipt.get("status") or "")
    if c_status == "failed" or a_status == "failed" or refused:
        status = "failed"
    elif c_status == "incomplete" or a_status == "incomplete" or not written:
        status = "incomplete"

    diffs = [row.get("diff") or "" for row in written if row.get("diff")]
    return {
        "version": CHANGE_EXECUTION_VERSION,
        "status": status,
        "slice_id": str(constraints.get("slice_id") or ""),
        "changed_files": [
            {
                "path": row.get("path"),
                "sha256_before": row.get("sha256_before"),
                "sha256_after": row.get("sha256_after"),
            }
            for row in written
        ],
        "diff": "\n".join(d for d in diffs if d),
        "scope_violations": [
            row for row in refused if row.get("reason") in {"scope_escape", "workspace_escape"}
        ],
        "refused": refused,
        "write_grants_required": list(
            constraints.get("write_grants_required") or [WRITE_GRANT]
        ),
        "allowed_paths": list(constraints.get("allowed_paths") or []),
        "provenance": {
            "title": constraints.get("title"),
            "rollback": constraints.get("rollback"),
            "written_count": len(written),
        },
    }


def validate_change_execution(result: Mapping[str, Any]) -> dict[str, Any]:
    """Schema report for a ChangeExecution (non-raising)."""
    errors: list[dict[str, str]] = []
    if str(result.get("version") or "") != CHANGE_EXECUTION_VERSION:
        errors.append(
            {"path": "version", "message": f"expected {CHANGE_EXECUTION_VERSION}"}
        )
    status = str(result.get("status") or "")
    if status not in {"ok", "incomplete", "failed"}:
        errors.append({"path": "status", "message": "ok|incomplete|failed required"})
    if not isinstance(result.get("changed_files"), list):
        errors.append({"path": "changed_files", "message": "list required"})
    if not isinstance(result.get("scope_violations"), list):
        errors.append({"path": "scope_violations", "message": "list required"})
    if WRITE_GRANT not in (result.get("write_grants_required") or []):
        errors.append(
            {
                "path": "write_grants_required",
                "message": f"{WRITE_GRANT} required",
            }
        )
    if status == "ok":
        if not result.get("slice_id"):
            errors.append({"path": "slice_id", "message": "required when ok"})
        if not result.get("changed_files"):
            errors.append({"path": "changed_files", "message": "non-empty when ok"})
        if result.get("scope_violations"):
            errors.append(
                {"path": "scope_violations", "message": "must be empty when ok"}
            )
        for index, row in enumerate(result.get("changed_files") or []):
            if not isinstance(row, Mapping):
                errors.append(
                    {"path": f"changed_files[{index}]", "message": "object required"}
                )
                continue
            if not row.get("path") or not row.get("sha256_after"):
                errors.append(
                    {
                        "path": f"changed_files[{index}]",
                        "message": "path and sha256_after required",
                    }
                )
    return {"ok": not errors, "errors": errors}


__all__ = [
    "CHANGE_EXECUTION_VERSION",
    "WRITE_GRANT",
    "apply_file_revisions",
    "assemble_change_execution",
    "extract_execution_constraints",
    "validate_change_execution",
]
