"""Data-driven host_kit dispatch / resume matrix interpreter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mechaharness.budget import BudgetPolicy
from mechaharness.external_effect import EffectDispatchResult, EffectRecord, EffectState
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.host_kit import (
    SubmitOnceEffectfulRunner,
    effectful_external_handle,
    host_graph_executor,
)
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore

CASES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "host_kit"

_EFFECT_STATES = {s.value: s for s in EffectState}
_NODE_STATUSES = {s.value: s for s in NodeStatus}


@dataclass
class SubmitLog:
    """Counts submit calls for non-idempotent dispatch asserts."""

    count: int = 0
    handles: list[str] = field(default_factory=list)

    async def submit(
        self,
        node: GraphNode,
        effect: EffectRecord,
        context: object,
    ) -> EffectDispatchResult:
        del effect, context
        self.count += 1
        handle = f"job-{node.payload.get('task_id') or node.id}-{self.count}"
        self.handles.append(handle)
        return EffectDispatchResult(
            external_handle=handle,
            detail={"backend_id": "test"},
        )


@dataclass(frozen=True)
class HostKitCase:
    """One fixture file under ``tests/fixtures/host_kit/``."""

    path: Path
    data: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.data.get("id") or self.path.stem)


def iter_cases() -> list[HostKitCase]:
    if not CASES_DIR.is_dir():
        return []
    cases: list[HostKitCase] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"{path}: case root must be an object")
        cases.append(HostKitCase(path=path, data=data))
    return cases


def make_graph(*, node_id: str = "coding_job", task_id: str = "t1") -> ExecutionGraph:
    graph = ExecutionGraph(id="g1", goal="host-kit")
    graph.add_node(
        GraphNode(
            id=node_id,
            kind="coding_job",
            goal="submit",
            payload={"task_id": task_id},
        )
    )
    return graph


async def run_case(case: HostKitCase, *, db_path: Path | None) -> dict[str, Any]:
    """Execute one host_kit fixture; return actual outcomes for soft expect."""
    mode = str(case.data.get("mode") or "dispatch")
    node_id = str(case.data.get("node_id") or "coding_job")
    task_id = str(case.data.get("task_id") or "t1")
    run_id = str(case.data.get("run_id") or f"hk-{case.id}")
    durable = bool(case.data.get("durable", True))
    log = SubmitLog()
    runner = SubmitOnceEffectfulRunner(
        kinds=["coding_job"],
        backend_id="test.coding",
        submit=log.submit,
    )

    if durable:
        if db_path is None:
            raise ValueError("durable cases require db_path")
        executor = host_graph_executor(
            runners=[runner],
            checkpoint_path=db_path,
            agent_id="host-kit-test",
        )
        store = executor.store
    else:
        executor = host_graph_executor(runners=[runner], agent_id="host-kit-test")
        store = executor.store

    if mode == "dispatch":
        result = await executor.run(
            make_graph(node_id=node_id, task_id=task_id),
            budget_policy=BudgetPolicy.unlimited(),
            run_id=run_id,
            skip_linkage=True,
        )
    elif mode == "resume_seeded":
        if not durable or not isinstance(store, SqliteCheckpointStore):
            raise ValueError("resume_seeded requires durable SqliteCheckpointStore")
        seed = dict(case.data.get("seed") or {})
        effect_state = _EFFECT_STATES[str(seed.get("effect_state") or "uncertain")]
        handle = seed.get("external_handle")
        attempt = int(seed.get("node_attempt") or 1)
        node_status = _NODE_STATUSES[str(seed.get("node_status") or "running")]
        graph = make_graph(node_id=node_id, task_id=task_id)
        graph.nodes[node_id].attempt = attempt
        graph.nodes[node_id].status = node_status
        store.save_effect(
            EffectRecord(
                effect_id=f"{run_id}:{node_id}:{attempt}",
                run_id=run_id,
                node_id=node_id,
                node_attempt=attempt,
                backend_id="test.coding",
                state=effect_state,
                external_handle=str(handle) if handle else None,
                recovery_boundary="dispatch",
            )
        )
        store.save(graph, run_id=run_id, boundary="dispatch", fingerprint="fp")
        result = await executor.run(
            make_graph(node_id=node_id, task_id=task_id),
            budget_policy=BudgetPolicy.unlimited(),
            run_id=run_id,
            resume=True,
            skip_linkage=True,
        )
    else:
        raise ValueError(f"unknown host_kit case mode: {mode!r}")

    effect = None
    if hasattr(store, "get_node_effect"):
        effect = store.get_node_effect(run_id=run_id, node_id=node_id)
    node = result.graph.nodes.get(node_id)
    actual = {
        "status": result.status,
        "node_status": node.status.value if node is not None else None,
        "dispatch_count": log.count,
        "external_handle": effectful_external_handle(result, node_id),
        "effect_state": effect.state.value if effect is not None else None,
        "effect_handle": effect.external_handle if effect is not None else None,
        "durability": store.durability,
        "error": node.error if node is not None else result.error,
        "result_error": result.error,
        "reconciliation_invoked": bool(result.diagnostics.get("reconciliation_invoked")),
    }
    if hasattr(store, "close"):
        store.close()
    return {"actual": actual, "expect": dict(case.data.get("expect") or {})}


def assert_expect(actual: dict[str, Any], expect: dict[str, Any], *, case_id: str) -> None:
    for key, wanted in expect.items():
        got = actual.get(key)
        assert got == wanted, f"case {case_id}: {key} expected {wanted!r}, got {got!r}"
