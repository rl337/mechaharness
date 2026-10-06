"""External-effect records, reconciliation, and crash probes (DR-03..07).

:class:`~mechaharness.graph_executor.EffectfulGraphNodeRunner` lives beside
``GraphNodeRunner`` so the registry stays a single injectable type.

Effect identity is generic — Cursor (or any coding-job backend) is a host
adapter detail, not a MechaHarness core type::

    >>> from mechaharness.external_effect import (
    ...     ArmedCrashProbe, EffectRecord, EffectState, InjectedProcessCrash,
    ... )
    >>> effect = EffectRecord(
    ...     effect_id="run:job:1",
    ...     run_id="run",
    ...     node_id="job",
    ...     node_attempt=1,
    ...     backend_id="host.coding_job",
    ...     state=EffectState.UNCERTAIN,
    ... )
    >>> effect.state.value
    'uncertain'
    >>> probe = ArmedCrashProbe("after_accept_before_record")
    >>> probe.maybe_crash("before_intent")  # not armed here
    >>> try:
    ...     probe.maybe_crash("after_accept_before_record", effect_id=effect.effect_id)
    ... except InjectedProcessCrash as crash:
    ...     crash.boundary
    'after_accept_before_record'
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.graph import RecoveryBoundary


class EffectState(str, Enum):
    """Durable lifecycle of an externally visible side effect.

    Distinguishes (DR-04):
    1. no record — dispatch was never intended;
    2. ``intended`` — intent committed, external call not started;
    3. ``uncertain`` — call may have started; acceptance unknown;
    4. ``accepted`` — external system accepted; handle recorded;
    5. ``completed`` / ``failed`` — terminal;
    6. ``needs_attention`` — host must decide; never silent redispatch.
    """

    INTENDED = "intended"
    UNCERTAIN = "uncertain"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"


class EffectRecord(BaseModel):
    """Persisted external-effect identity (DR-03)."""

    model_config = ConfigDict(extra="allow")

    effect_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    node_id: str
    node_attempt: int = 0
    backend_id: str = ""
    external_handle: str | None = None
    state: EffectState = EffectState.INTENDED
    revision: int = 0
    recovery_boundary: RecoveryBoundary | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class EffectReconciliationAction(str, Enum):
    """Host adapter decision after inspecting an uncertain/accepted effect."""

    DISPATCH = "dispatch"
    OBSERVE = "observe"
    COMPLETE = "complete"
    FAIL = "fail"
    NEEDS_ATTENTION = "needs_attention"


class EffectReconciliation(BaseModel):
    """Result of host-side reconcile (DR-06)."""

    model_config = ConfigDict(extra="allow")

    action: EffectReconciliationAction
    external_handle: str | None = None
    outcome_payload: dict[str, Any] = Field(default_factory=dict)
    outcome_evidence: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class EffectDispatchResult(BaseModel):
    """Return value of an external dispatch once the backend accepts it."""

    model_config = ConfigDict(extra="allow")

    external_handle: str
    detail: dict[str, Any] = Field(default_factory=dict)


class InjectedProcessCrash(Exception):
    """Simulated process death at a recovery boundary (acceptance tests)."""

    def __init__(self, boundary: str, *, detail: dict[str, Any] | None = None) -> None:
        self.boundary = boundary
        self.detail = dict(detail or {})
        super().__init__(f"injected_process_crash:{boundary}")


CrashLocation = Literal[
    "before_intent",
    "after_intent_before_call",
    "after_accept_before_record",
    "after_accept_recorded",
    "after_reduce_before_checkpoint",
    "after_final_commit",
]


class CrashProbe(ABC):
    """Optional injectable that raises :class:`InjectedProcessCrash` at a boundary."""

    @abstractmethod
    def maybe_crash(self, location: CrashLocation, **ctx: Any) -> None:
        """Raise if this probe is armed for ``location``."""


class NoopCrashProbe(CrashProbe):
    """Default: never crash."""

    def maybe_crash(self, location: CrashLocation, **ctx: Any) -> None:
        del location, ctx


class ArmedCrashProbe(CrashProbe):
    """Raise once at a single crash location (for DR-10 / DR-12 matrices)."""

    def __init__(self, location: CrashLocation) -> None:
        self.location = location
        self.triggered = False

    def maybe_crash(self, location: CrashLocation, **ctx: Any) -> None:
        if self.triggered or location != self.location:
            return
        self.triggered = True
        raise InjectedProcessCrash(location, detail=dict(ctx))
