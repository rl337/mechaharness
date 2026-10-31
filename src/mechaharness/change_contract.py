"""Typed ChangeContract helpers (gastronomic M6 contract extraction).

A ChangeContract freezes prior invariants and requested behavior before any
mutating coding step. Model proposals cannot drop verified inventory evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

CHANGE_CONTRACT_VERSION = "1"


def freeze_prior_invariants(
    inventory: Mapping[str, Any],
    *,
    goal: str = "",
) -> list[dict[str, Any]]:
    """Build immutable path+hash invariants from a verified WorkspaceInventory."""
    invariants: list[dict[str, Any]] = []
    for row in inventory.get("relevant_files") or []:
        if not isinstance(row, Mapping):
            continue
        path = str(row.get("path") or "")
        if not path:
            continue
        inv_id = f"preserve:{path}"
        invariants.append(
            {
                "id": inv_id,
                "description": f"Preserve verified evidence at {path}",
                "path": path,
                "sha256": row.get("sha256"),
                "evidence_id": row.get("evidence_id") or f"verified:{path}",
                "immutable": True,
            }
        )
    for row in inventory.get("tests") or []:
        if not isinstance(row, Mapping):
            continue
        path = str(row.get("path") or "")
        if not path:
            continue
        inv_id = f"tests_green:{path}"
        if any(item["id"] == inv_id for item in invariants):
            continue
        invariants.append(
            {
                "id": inv_id,
                "description": f"Keep tests green for {path}",
                "path": path,
                "sha256": row.get("sha256"),
                "evidence_id": row.get("evidence_id") or f"verified:{path}",
                "immutable": True,
                "check": {"pytest": True, "path": path},
            }
        )
    if goal and not invariants:
        invariants.append(
            {
                "id": "objective_context",
                "description": "Retain caller objective while planning changes",
                "immutable": False,
                "objective": goal,
            }
        )
    return invariants


def assemble_change_contract(
    *,
    goal: Any,
    inventory: Mapping[str, Any],
    proposed: Mapping[str, Any] | None = None,
    frozen_invariants: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge proposed semantics with frozen invariants into a ChangeContract."""
    objective = goal if isinstance(goal, str) else str(goal or "")
    proposed_map = proposed if isinstance(proposed, Mapping) else {}
    frozen = [
        dict(row)
        for row in (frozen_invariants or freeze_prior_invariants(inventory, goal=objective))
        if isinstance(row, Mapping)
    ]
    frozen_ids = {str(row.get("id") or "") for row in frozen}

    extra_invariants: list[dict[str, Any]] = []
    for row in proposed_map.get("invariants") or []:
        if not isinstance(row, Mapping):
            continue
        inv_id = str(row.get("id") or "")
        if inv_id and inv_id in frozen_ids:
            # Model cannot replace an immutable prior invariant by id.
            continue
        if row.get("immutable") is True and inv_id.startswith("preserve:"):
            continue
        extra_invariants.append(dict(row))

    status = "ok"
    inv_status = str(inventory.get("status") or "")
    if inv_status == "failed":
        status = "failed"
    elif inv_status in {"inconclusive", "not_found"}:
        status = "incomplete"
    elif proposed_map.get("status") == "failed":
        status = "failed"

    verification: list[dict[str, Any]] = []
    for row in proposed_map.get("verification") or []:
        if isinstance(row, Mapping):
            verification.append(dict(row))
    for row in frozen:
        check = row.get("check")
        if isinstance(check, Mapping):
            verification.append(dict(check))

    return {
        "version": CHANGE_CONTRACT_VERSION,
        "status": status,
        "objective": objective,
        "requested_behavior": proposed_map.get("requested_behavior")
        or objective,
        "invariants": frozen + extra_invariants,
        "prohibited_changes": list(proposed_map.get("prohibited_changes") or []),
        "verification": verification,
        "assumptions": list(proposed_map.get("assumptions") or []),
        "unknowns": list(proposed_map.get("unknowns") or [])
        + list(inventory.get("unknowns") or []),
        "provenance": {
            "workspace_revision": inventory.get("workspace_revision"),
            "discovery_status": inv_status,
            "relevant_paths": [
                str(r.get("path"))
                for r in (inventory.get("relevant_files") or [])
                if isinstance(r, Mapping) and r.get("path")
            ],
        },
    }


def validate_change_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Schema report for a ChangeContract (non-raising)."""
    errors: list[dict[str, str]] = []
    if str(contract.get("version") or "") != CHANGE_CONTRACT_VERSION:
        errors.append({"path": "version", "message": f"expected {CHANGE_CONTRACT_VERSION}"})
    if not str(contract.get("objective") or "").strip():
        errors.append({"path": "objective", "message": "non-empty string required"})
    if not isinstance(contract.get("invariants"), list):
        errors.append({"path": "invariants", "message": "list required"})
    if not isinstance(contract.get("verification"), list):
        errors.append({"path": "verification", "message": "list required"})
    status = str(contract.get("status") or "")
    if status not in {"ok", "incomplete", "failed"}:
        errors.append({"path": "status", "message": "ok|incomplete|failed required"})
    return {"ok": not errors, "errors": errors}


__all__ = [
    "CHANGE_CONTRACT_VERSION",
    "assemble_change_contract",
    "freeze_prior_invariants",
    "validate_change_contract",
]
