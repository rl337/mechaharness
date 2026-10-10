"""Host kit: Config-injected GraphExecutor + submit-once effectful runner."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mechaharness.budget import BudgetPolicy
from mechaharness.external_effect import EffectDispatchResult
from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.host_kit import (
    SubmitOnceEffectfulRunner,
    effectful_external_handle,
    host_graph_executor,
)


def test_submit_once_dispatches_once_and_exposes_handle(tmp_path: Path) -> None:
    calls = {"n": 0}

    async def submit(node, effect, context):  # noqa: ANN001
        del effect, context
        calls["n"] += 1
        return EffectDispatchResult(
            external_handle=f"job-{node.payload.get('task_id')}",
            detail={"backend_id": "test"},
        )

    runner = SubmitOnceEffectfulRunner(
        kinds=["coding_job"],
        backend_id="test.coding",
        submit=submit,
    )
    ckpt = tmp_path / "ckpt.sqlite"
    executor = host_graph_executor(
        runners=[runner],
        checkpoint_path=ckpt,
        agent_id="june-test",
    )
    graph = ExecutionGraph(id="g1", goal="dispatch")
    graph.add_node(
        GraphNode(
            id="coding_job",
            kind="coding_job",
            goal="submit",
            payload={"task_id": "t1"},
        )
    )
    result = asyncio.run(
        executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            run_id="run-1",
            skip_linkage=True,
        )
    )
    assert result.status == "ok"
    assert calls["n"] == 1
    assert effectful_external_handle(result, "coding_job") == "job-t1"
    assert executor.store.durability == "durable"
    assert ckpt.exists()


def test_host_graph_executor_ephemeral_without_checkpoint() -> None:
    async def submit(node, effect, context):  # noqa: ANN001
        del node, effect, context
        return EffectDispatchResult(external_handle="ephemeral-1")

    runner = SubmitOnceEffectfulRunner(
        kinds=["coding_job"],
        backend_id="test",
        submit=submit,
    )
    executor = host_graph_executor(runners=[runner])
    graph = ExecutionGraph(goal="ephemeral")
    graph.add_node(GraphNode(id="coding_job", kind="coding_job"))
    result = asyncio.run(
        executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            run_id="run-e",
            skip_linkage=True,
        )
    )
    assert result.status == "ok"
    assert effectful_external_handle(result, "coding_job") == "ephemeral-1"
    assert executor.store.durability == "ephemeral"
