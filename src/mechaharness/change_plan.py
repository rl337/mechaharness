"""Typed ChangePlan helpers (gastronomic M6 change decomposition).

A ChangePlan turns a ChangeContract into small ordered slices with scope,
checks, rollback, and dependency order — before any mutating coding step.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

CHANGE_PLAN_VERSION = "1"


def extract_plan_constraints(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Project contract invariants/checks that plan slices must respect."""
    invariant_ids: list[str] = []
    for row in contract.get("invariants") or []:
        if isinstance(row, Mapping) and row.get("id"):
            invariant_ids.append(str(row["id"]))
    verification: list[dict[str, Any]] = []
    for row in contract.get("verification") or []:
        if isinstance(row, Mapping):
            verification.append(dict(row))
    return {
        "objective": str(contract.get("objective") or ""),
        "contract_status": str(contract.get("status") or ""),
        "invariant_ids": invariant_ids,
        "prohibited_changes": list(contract.get("prohibited_changes") or []),
        "verification": verification,
        "relevant_paths": list(
            (contract.get("provenance") or {}).get("relevant_paths") or []
            if isinstance(contract.get("provenance"), Mapping)
            else []
        ),
    }


def _normalize_slice(raw: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    slice_id = str(raw.get("id") or f"slice_{index + 1}").strip()
    scope_raw = raw.get("scope")
    if isinstance(scope_raw, Mapping):
        scope = dict(scope_raw)
    elif isinstance(scope_raw, str) and scope_raw.strip():
        scope = {"description": scope_raw.strip()}
    else:
        scope = {}
    if "paths" in scope and not isinstance(scope["paths"], list):
        scope["paths"] = [str(scope["paths"])]
    checks: list[dict[str, Any]] = []
    for row in raw.get("checks") or []:
        if isinstance(row, Mapping):
            checks.append(dict(row))
        elif isinstance(row, str) and row.strip():
            checks.append({"command": row.strip()})
    depends_on = [
        str(item)
        for item in (raw.get("depends_on") or [])
        if str(item).strip()
    ]
    return {
        "id": slice_id,
        "title": str(raw.get("title") or raw.get("description") or slice_id),
        "scope": scope,
        "checks": checks,
        "rollback": str(raw.get("rollback") or ""),
        "depends_on": depends_on,
        "risks": list(raw.get("risks") or []),
    }


def _topological_order(slices: Sequence[Mapping[str, Any]]) -> list[str] | None:
    """Return slice ids in dependency order, or None if a cycle/unknown edge."""
    by_id = {str(row["id"]): row for row in slices}
    indegree = {sid: 0 for sid in by_id}
    children: dict[str, list[str]] = {sid: [] for sid in by_id}
    for row in slices:
        sid = str(row["id"])
        for dep in row.get("depends_on") or []:
            dep_id = str(dep)
            if dep_id not in by_id:
                return None
            children[dep_id].append(sid)
            indegree[sid] += 1
    queue = sorted(sid for sid, deg in indegree.items() if deg == 0)
    ordered: list[str] = []
    while queue:
        sid = queue.pop(0)
        ordered.append(sid)
        for child in children[sid]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort()
    if len(ordered) != len(by_id):
        return None
    return ordered


def assemble_change_plan(
    *,
    contract: Mapping[str, Any],
    proposed: Mapping[str, Any] | None = None,
    constraints: Mapping[str, Any] | None = None,
    inventory: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge proposed slices with hard schema/dependency checks into a ChangePlan."""
    proposed_map = proposed if isinstance(proposed, Mapping) else {}
    frozen = constraints if isinstance(constraints, Mapping) else extract_plan_constraints(
        contract
    )
    objective = str(
        proposed_map.get("objective")
        or frozen.get("objective")
        or contract.get("objective")
        or ""
    )

    raw_slices = proposed_map.get("slices") or []
    slices: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(raw_slices):
        if not isinstance(row, Mapping):
            continue
        normalized = _normalize_slice(row, index=index)
        if normalized["id"] in seen_ids:
            normalized["id"] = f"{normalized['id']}_{index + 1}"
        seen_ids.add(normalized["id"])
        # Inherit contract verification when the model omitted checks.
        if not normalized["checks"] and frozen.get("verification"):
            normalized["checks"] = [dict(c) for c in frozen["verification"]]
        slices.append(normalized)

    status = "ok"
    contract_status = str(contract.get("status") or frozen.get("contract_status") or "")
    if contract_status == "failed" or proposed_map.get("status") == "failed":
        status = "failed"
    elif contract_status == "incomplete" or not slices:
        status = "incomplete"

    order = _topological_order(slices) if slices else []
    if slices and order is None:
        status = "failed"
        ordered_slices = slices
    else:
        by_id = {row["id"]: row for row in slices}
        ordered_slices = []
        for position, sid in enumerate(order or []):
            row = dict(by_id[sid])
            row["order"] = position
            ordered_slices.append(row)

    return {
        "version": CHANGE_PLAN_VERSION,
        "status": status,
        "objective": objective,
        "slices": ordered_slices,
        "constraints": dict(frozen),
        "provenance": {
            "contract_status": contract_status,
            "invariant_ids": list(frozen.get("invariant_ids") or []),
            "inventory_status": (
                str(inventory.get("status") or "")
                if isinstance(inventory, Mapping)
                else ""
            ),
            "slice_count": len(ordered_slices),
        },
    }


def validate_change_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Schema report for a ChangePlan (non-raising)."""
    errors: list[dict[str, str]] = []
    if str(plan.get("version") or "") != CHANGE_PLAN_VERSION:
        errors.append({"path": "version", "message": f"expected {CHANGE_PLAN_VERSION}"})
    if not str(plan.get("objective") or "").strip():
        errors.append({"path": "objective", "message": "non-empty string required"})
    slices = plan.get("slices")
    if not isinstance(slices, list):
        errors.append({"path": "slices", "message": "list required"})
        slices = []
    status = str(plan.get("status") or "")
    if status not in {"ok", "incomplete", "failed"}:
        errors.append({"path": "status", "message": "ok|incomplete|failed required"})
    ids: set[str] = set()
    for index, row in enumerate(slices):
        if not isinstance(row, Mapping):
            errors.append({"path": f"slices[{index}]", "message": "object required"})
            continue
        sid = str(row.get("id") or "")
        if not sid:
            errors.append({"path": f"slices[{index}].id", "message": "required"})
        elif sid in ids:
            errors.append({"path": f"slices[{index}].id", "message": "duplicate id"})
        else:
            ids.add(sid)
        if not str(row.get("title") or "").strip():
            errors.append({"path": f"slices[{index}].title", "message": "required"})
        scope = row.get("scope")
        if not isinstance(scope, Mapping) or not (
            scope.get("paths") or scope.get("description")
        ):
            errors.append(
                {
                    "path": f"slices[{index}].scope",
                    "message": "paths or description required",
                }
            )
        if not isinstance(row.get("checks"), list) or not row.get("checks"):
            errors.append({"path": f"slices[{index}].checks", "message": "non-empty list"})
        if not str(row.get("rollback") or "").strip():
            errors.append({"path": f"slices[{index}].rollback", "message": "required"})
    all_ids = {
        str(s.get("id"))
        for s in slices
        if isinstance(s, Mapping) and s.get("id")
    }
    for index, row in enumerate(slices):
        if not isinstance(row, Mapping):
            continue
        for dep in row.get("depends_on") or []:
            if str(dep) not in all_ids:
                errors.append(
                    {
                        "path": f"slices[{index}].depends_on",
                        "message": f"unknown dependency {dep!r}",
                    }
                )
    if slices:
        order = _topological_order(
            [row for row in slices if isinstance(row, Mapping)]
        )
        if order is None:
            errors.append({"path": "slices", "message": "dependency cycle or unknown edge"})
    return {"ok": not errors, "errors": errors}


__all__ = [
    "CHANGE_PLAN_VERSION",
    "assemble_change_plan",
    "extract_plan_constraints",
    "validate_change_plan",
]
