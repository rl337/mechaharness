"""Product CLI verb: crash-window durable resume for external coding-job effects.

Hosts (and stories) exercise DR-10 crash locations through the same
:func:`~mechaharness.host_kit.host_graph_executor` seam used in production,
with an optional :class:`~mechaharness.external_effect.ArmedCrashProbe` for
acceptance matrices. The demo coding-job backend is host-shaped reference
wiring — real hosts swap in their own effectful runner.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from pyiv.time import MockDateTimeService

from mechaharness.budget import BudgetPolicy
from mechaharness.cli_verb import CliVerb
from mechaharness.external_effect import (
    ArmedCrashProbe,
    CrashLocation,
    CrashProbe,
    EffectDispatchResult,
    EffectReconciliation,
    EffectReconciliationAction,
    EffectRecord,
    EffectState,
    InjectedProcessCrash,
    NoopCrashProbe,
)
from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.graph_executor import (
    EffectfulGraphNodeRunner,
    GraphExecutor,
    GraphRunContext,
)
from mechaharness.host_kit import host_graph_executor
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore


class TransactionalResumeCommand(BaseModel):
    """Run a coding_job node through crash + durable resume for one location."""

    model_config = ConfigDict(extra="forbid")

    crash_location: CrashLocation
    goal: str = "downstream-coding-job"
    run_id_prefix: str = "story-tdr"


class DemoCodingJobBackend:
    """Deterministic host-shaped coding-job backend (no network)."""

    def __init__(self) -> None:
        self.dispatch_count = 0
        self.reconcile_count = 0
        self.observe_count = 0
        self.jobs: dict[str, dict[str, Any]] = {}
        self.unknown_effect_ids: set[str] = set()

    def dispatch(self, effect_id: str) -> str:
        self.dispatch_count += 1
        handle = f"cursor-job-{effect_id}"
        self.jobs[effect_id] = {"handle": handle, "status": "running"}
        return handle

    def lookup(self, effect_id: str, handle: str | None) -> dict[str, Any] | None:
        if effect_id in self.unknown_effect_ids:
            return None
        job = self.jobs.get(effect_id)
        if job is not None:
            return job
        if handle is not None:
            for item in self.jobs.values():
                if item.get("handle") == handle:
                    return item
        return None

    def complete(self, effect_id: str) -> dict[str, Any]:
        job = self.jobs.setdefault(
            effect_id, {"handle": f"cursor-job-{effect_id}", "status": "running"}
        )
        job["status"] = "completed"
        job["result"] = {"diff": "ok", "effect_id": effect_id}
        return job


class DemoCodingJobEffectRunner(EffectfulGraphNodeRunner):
    """Maps :class:`DemoCodingJobBackend` into the effect contract."""

    def __init__(self, backend: DemoCodingJobBackend) -> None:
        self.backend = backend

    def kinds(self) -> list[str]:
        return ["coding_job"]

    def backend_id(self) -> str:
        return "demo.coding_job"

    async def reconcile(
        self,
        node: GraphNode,
        *,
        effect: EffectRecord,
        context: GraphRunContext,
    ) -> EffectReconciliation:
        del node, context
        self.backend.reconcile_count += 1
        job = self.backend.lookup(effect.effect_id, effect.external_handle)
        if job is None:
            if effect.state is EffectState.INTENDED:
                return EffectReconciliation(action=EffectReconciliationAction.DISPATCH)
            if effect.state is EffectState.UNCERTAIN:
                return EffectReconciliation(
                    action=EffectReconciliationAction.NEEDS_ATTENTION,
                    error="uncertain_effect_unresolved",
                )
            return EffectReconciliation(
                action=EffectReconciliationAction.NEEDS_ATTENTION,
                error="effect_not_found",
            )
        handle = str(job["handle"])
        if job.get("status") == "completed":
            return EffectReconciliation(
                action=EffectReconciliationAction.COMPLETE,
                external_handle=handle,
                outcome_payload=dict(job.get("result") or {}),
                outcome_evidence={"job_status": "completed"},
            )
        return EffectReconciliation(
            action=EffectReconciliationAction.OBSERVE,
            external_handle=handle,
        )

    async def dispatch(
        self,
        node: GraphNode,
        *,
        effect: EffectRecord,
        context: GraphRunContext,
    ) -> EffectDispatchResult:
        del node, context
        handle = self.backend.dispatch(effect.effect_id)
        return EffectDispatchResult(external_handle=handle)

    async def observe(
        self,
        node: GraphNode,
        *,
        effect: EffectRecord,
        context: GraphRunContext,
    ) -> EffectReconciliation:
        del node, context
        self.backend.observe_count += 1
        job = self.backend.complete(effect.effect_id)
        return EffectReconciliation(
            action=EffectReconciliationAction.COMPLETE,
            external_handle=str(job["handle"]),
            outcome_payload=dict(job.get("result") or {}),
            outcome_evidence={"job_status": "completed"},
        )


def _tdr_executor(
    *,
    store: SqliteCheckpointStore,
    backend: DemoCodingJobBackend,
    crash: CrashProbe,
) -> GraphExecutor:
    return host_graph_executor(
        runners=[DemoCodingJobEffectRunner(backend)],
        checkpoint_store=store,
        crash_probe=crash,
        grants=None,  # default GraphExecute + GraphEscalate
    )


def _coding_job_graph(goal: str) -> ExecutionGraph:
    graph = ExecutionGraph(goal=goal)
    graph.add_node(GraphNode(id="dispatch", kind="coding_job", max_attempts=3))
    return graph


async def run_transactional_resume(body: TransactionalResumeCommand) -> dict[str, Any]:
    """Crash at ``crash_location``, then resume the same SQLite-backed run."""
    clock = MockDateTimeService(datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc))
    location = body.crash_location
    with tempfile.TemporaryDirectory(prefix="mh-tdr-") as tmp:
        db = Path(tmp) / f"{location}.sqlite"
        store = SqliteCheckpointStore(db, datetime_service=clock)
        backend = DemoCodingJobBackend()
        run_id = f"{body.run_id_prefix}-{location}"
        first = _tdr_executor(
            store=store, backend=backend, crash=ArmedCrashProbe(location)
        )
        crashed = False
        try:
            await first.run(
                _coding_job_graph(body.goal),
                budget_policy=BudgetPolicy.unlimited(),
                run_id=run_id,
            )
        except InjectedProcessCrash:
            crashed = True
        effect_before = store.get_node_effect(run_id=run_id, node_id="dispatch")
        boundary_before = store.latest_boundary(run_id=run_id)
        dispatch_after_crash = backend.dispatch_count
        resumed = _tdr_executor(
            store=store, backend=backend, crash=NoopCrashProbe()
        )
        result = await resumed.run(
            _coding_job_graph(body.goal),
            budget_policy=BudgetPolicy.unlimited(),
            run_id=run_id,
            resume=True,
        )
        effect_after = store.get_node_effect(run_id=run_id, node_id="dispatch")
        node = result.graph.nodes["dispatch"]
        spent = float(result.budget_spent)
        out = {
            "crashed": crashed,
            "status": result.status,
            "node_status": node.status.value,
            "dispatch_count": backend.dispatch_count,
            "dispatch_count_after_crash": dispatch_after_crash,
            "effect_state_before": (
                effect_before.state.value if effect_before else None
            ),
            "effect_state_after": (
                effect_after.state.value if effect_after else None
            ),
            "reconciliation_invoked": bool(
                result.diagnostics.get("reconciliation_invoked")
            ),
            "boundary_before": boundary_before,
            "budget_spent": spent,
            "cost_units": spent,
        }
        store.close()
        return out


class TransactionalResumeVerb(CliVerb):
    """Product verb: durable coding-job dispatch through one crash window."""

    name = "transactional_resume"
    params_model = TransactionalResumeCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        return await run_transactional_resume(params)  # type: ignore[arg-type]


__all__ = [
    "DemoCodingJobBackend",
    "DemoCodingJobEffectRunner",
    "TransactionalResumeCommand",
    "TransactionalResumeVerb",
    "run_transactional_resume",
]
