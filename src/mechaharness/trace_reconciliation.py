"""Reconcile independent observation surfaces (MH-MHRL-09).

FineEnvs compares proxy capture against Harbor's independently written ATIF
trajectory and rejects mismatches
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#rewards).

MechaHarness reconciles executor events, model-gateway/manifest capture,
tool/runtime audit logs, and optional sandbox/client transitions::

    >>> from mechaharness.trace_reconciliation import (
    ...     ObservationSurface, reconcile_traces, require_reconciled,
    ... )
    >>> report = reconcile_traces([
    ...     ObservationSurface(name="executor", event_ids=["a", "b"]),
    ...     ObservationSurface(name="gateway", event_ids=["a", "b"]),
    ... ])
    >>> report.status
    'agree'
    >>> require_reconciled(report).status
    'agree'
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ReconcileStatus = Literal["agree", "missing", "conflict"]


class ObservationSurface(BaseModel):
    """One independent observation stream for a run."""

    model_config = ConfigDict(extra="allow")

    name: str
    event_ids: list[str] = Field(default_factory=list)
    digests: dict[str, str] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)


class TraceReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: ReconcileStatus = "agree"
    missing: dict[str, list[str]] = Field(default_factory=dict)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "agree"


def reconcile_traces(surfaces: Sequence[ObservationSurface]) -> TraceReconciliationReport:
    """Compare event ids and digests across observation surfaces."""
    if not surfaces:
        return TraceReconciliationReport(status="agree")
    names = [s.name for s in surfaces]
    union: set[str] = set()
    for surface in surfaces:
        union.update(surface.event_ids)
    missing: dict[str, list[str]] = {}
    for surface in surfaces:
        absent = sorted(union - set(surface.event_ids))
        if absent:
            missing[surface.name] = absent
    conflicts: list[dict[str, Any]] = []
    # Compare digests for shared keys across pairs.
    for i, left in enumerate(surfaces):
        for right in surfaces[i + 1 :]:
            shared = set(left.digests) & set(right.digests)
            for key in sorted(shared):
                if left.digests[key] != right.digests[key]:
                    conflicts.append(
                        {
                            "key": key,
                            "left_surface": left.name,
                            "right_surface": right.name,
                            "left": left.digests[key],
                            "right": right.digests[key],
                        }
                    )
    if conflicts:
        status: ReconcileStatus = "conflict"
    elif missing:
        status = "missing"
    else:
        status = "agree"
    return TraceReconciliationReport(
        status=status,
        missing=missing,
        conflicts=conflicts,
        surfaces=names,
    )


def require_reconciled(report: TraceReconciliationReport) -> TraceReconciliationReport:
    if not report.ok:
        raise ValueError(f"trace reconciliation failed: {report.status}")
    return report
