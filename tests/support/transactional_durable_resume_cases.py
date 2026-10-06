"""Data-driven transactional durable-resume crash matrix (DR-10)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mechaharness.budget import BudgetPolicy
from mechaharness.checkpoint_store import CheckpointStore
from mechaharness.core.access import GraphExecute
from mechaharness.di import MechaHarnessConfig, get_injector
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
    GraphNodeRunnerRegistry,
    GraphRunContext,
)
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore

CASES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "transactional_durable_resume"


@dataclass
class FakeCodingJobBackend:
    """Downstream-client-shaped fake coding-job backend (deterministic, no network)."""

    dispatch_count: int = 0
    reconcile_count: int = 0
    observe_count: int = 0
    jobs: dict[str, dict[str, Any]] | None = None
    unknown_effect_ids: set[str] | None = None

    def __post_init__(self) -> None:
        if self.jobs is None:
            self.jobs = {}
        if self.unknown_effect_ids is None:
            self.unknown_effect_ids = set()

    def dispatch(self, effect_id: str) -> str:
        assert self.jobs is not None
        self.dispatch_count += 1
        handle = f"cursor-job-{effect_id}"
        self.jobs[effect_id] = {"handle": handle, "status": "running"}
        return handle

    def lookup(self, effect_id: str, handle: str | None) -> dict[str, Any] | None:
        assert self.jobs is not None
        assert self.unknown_effect_ids is not None
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
        assert self.jobs is not None
        job = self.jobs.setdefault(
            effect_id, {"handle": f"cursor-job-{effect_id}", "status": "running"}
        )
        job["status"] = "completed"
        job["result"] = {"diff": "ok", "effect_id": effect_id}
        return job


class CodingJobEffectRunner(EffectfulGraphNodeRunner):
    """Host-owned adapter: maps fake coding jobs into the effect contract."""

    def __init__(self, backend: FakeCodingJobBackend) -> None:
        self.backend = backend

    def kinds(self) -> list[str]:
        return ["coding_job"]

    def backend_id(self) -> str:
        return "fake.coding_job"

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
                # Acceptance genuinely unknowable → escalate, never redispatch.
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


@dataclass(frozen=True)
class TransactionalDurableResumeCase:
    path: Path
    data: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.data.get("id") or self.path.stem)

    @property
    def crash_location(self) -> CrashLocation:
        return self.data["crash_location"]  # type: ignore[return-value]


def iter_cases() -> list[TransactionalDurableResumeCase]:
    if not CASES_DIR.is_dir():
        return []
    cases: list[TransactionalDurableResumeCase] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"{path}: case root must be an object")
        cases.append(TransactionalDurableResumeCase(path=path, data=data))
    return cases


def build_executor(
    *,
    store: CheckpointStore,
    backend: FakeCodingJobBackend,
    crash: CrashProbe | None = None,
) -> GraphExecutor:
    registry = GraphNodeRunnerRegistry([CodingJobEffectRunner(backend)])
    probe = crash if crash is not None else NoopCrashProbe()

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

        def get_checkpoint_store(self) -> CheckpointStore:
            return store

        def get_crash_probe(self) -> CrashProbe:
            return probe

    return get_injector(Cfg()).inject(GraphExecutor)


def make_graph(goal: str = "coding-job") -> ExecutionGraph:
    graph = ExecutionGraph(goal=goal)
    graph.add_node(GraphNode(id="dispatch", kind="coding_job", max_attempts=3))
    return graph


async def run_crash_case(
    case: TransactionalDurableResumeCase,
    *,
    db_path: Path,
) -> dict[str, Any]:
    store = SqliteCheckpointStore(db_path)
    backend = FakeCodingJobBackend()
    run_id = str(case.data.get("run_id") or f"tdr-{case.id}")
    crash_at: CrashLocation = case.crash_location
    expect = dict(case.data.get("expect") or {})

    first = build_executor(
        store=store,
        backend=backend,
        crash=ArmedCrashProbe(crash_at),
    )
    graph = make_graph(str(case.data.get("goal") or "coding-job"))
    crashed = False
    try:
        await first.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            run_id=run_id,
        )
    except InjectedProcessCrash:
        crashed = True

    effect_before = store.get_node_effect(run_id=run_id, node_id="dispatch")
    boundary_before = store.latest_boundary(run_id=run_id)
    revision_before = store.latest_revision(run_id=run_id)
    dispatch_after_crash = backend.dispatch_count

    # Fresh executor + same durable store (process restart).
    resumed_exec = build_executor(store=store, backend=backend, crash=NoopCrashProbe())
    result = await resumed_exec.run(
        make_graph(str(case.data.get("goal") or "coding-job")),
        budget_policy=BudgetPolicy.unlimited(),
        run_id=run_id,
        resume=True,
    )
    effect_after = store.get_node_effect(run_id=run_id, node_id="dispatch")
    node = result.graph.nodes["dispatch"]

    actual = {
        "crashed": crashed,
        "status": result.status,
        "node_status": node.status.value,
        "dispatch_count": backend.dispatch_count,
        "dispatch_count_after_crash": dispatch_after_crash,
        "reconcile_count": backend.reconcile_count,
        "reconciliation_invoked": bool(
            result.diagnostics.get("reconciliation_invoked")
        ),
        "runner_reentered": bool(result.diagnostics.get("runner_reentered")),
        "effect_state_before": effect_before.state.value if effect_before else None,
        "effect_state_after": effect_after.state.value if effect_after else None,
        "external_handle": effect_after.external_handle if effect_after else None,
        "boundary_before": boundary_before,
        "boundary_after": store.latest_boundary(run_id=run_id),
        "revision_before": revision_before,
        "revision_after": store.latest_revision(run_id=run_id),
        "error": result.error,
        "checkpoint_durability": result.diagnostics.get("checkpoint_durability"),
    }
    store.close()
    return {"actual": actual, "expect": expect}


def assert_expect(actual: dict[str, Any], expect: dict[str, Any]) -> None:
    for key, wanted in expect.items():
        if key.endswith("_contains"):
            field = key[: -len("_contains")]
            hay = str(actual.get(field) or "")
            assert wanted in hay, f"{field} expected to contain {wanted!r}, got {hay!r}"
            continue
        assert actual.get(key) == wanted, f"{key}: expected {wanted!r}, got {actual.get(key)!r}"
