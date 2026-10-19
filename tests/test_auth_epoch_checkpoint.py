"""Authorization epoch persisted on checkpoints and checked on resume (MH-DOTS-06)."""

from __future__ import annotations

import pytest
from pyiv import get_injector

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import GraphExecute
from mechaharness.di import MechaHarnessConfig
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphExecutor,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore
from tests.support.stdlib_doubles import mock_datetime_service


def _executor(calls: list[str]) -> GraphExecutor:
    async def work(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        calls.append(node.id)
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], work)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    return get_injector(Cfg()).inject(GraphExecutor)


def _graph() -> ExecutionGraph:
    graph = ExecutionGraph(goal="epoch")
    graph.add_node(GraphNode(id="a", kind="compute"))
    return graph


def _env(epoch: int) -> CapabilityEnvelope:
    return CapabilityEnvelope(grants=["core:graph.execute"], authorization_epoch=epoch)


_RESUME_CASES = [
    # id, first epoch, resume epoch (None = no envelope), expected status
    ("same_epoch", 2, 2, "ok"),
    ("advanced_epoch", 2, 3, "failed"),
    ("regressed_epoch", 3, 2, "failed"),
    ("no_live_envelope_skips_check", 2, None, "ok"),
    ("legacy_zero_matches_zero", 0, 0, "ok"),
    ("legacy_zero_refused_after_revocation", 0, 1, "failed"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_id", "first", "second", "status"), _RESUME_CASES, ids=[c[0] for c in _RESUME_CASES]
)
async def test_resume_compares_authorization_epoch(
    case_id: str, first: int, second: int | None, status: str
) -> None:
    del case_id
    calls: list[str] = []
    executor = _executor(calls)
    graph = _graph()
    await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="r", envelope=_env(first)
    )
    assert executor.store.latest_authorization_epoch(run_id="r") == first
    calls.clear()
    resumed = await executor.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="r",
        resume=True,
        envelope=_env(second) if second is not None else None,
    )
    assert resumed.status == status
    if status == "failed":
        assert resumed.error == f"authorization_epoch_mismatch:{first}!={second}"
        assert calls == []


@pytest.mark.asyncio
async def test_mismatch_refusal_leaves_checkpoint_untouched() -> None:
    executor = _executor([])
    await executor.run(
        _graph(), budget_policy=BudgetPolicy.unlimited(), run_id="r", envelope=_env(1)
    )
    before = executor.store.latest_revision(run_id="r")
    await executor.run(
        _graph(),
        budget_policy=BudgetPolicy.unlimited(),
        run_id="r",
        resume=True,
        envelope=_env(2),
    )
    assert executor.store.latest_revision(run_id="r") == before
    assert executor.store.latest_authorization_epoch(run_id="r") == 1


@pytest.mark.asyncio
async def test_resume_without_checkpoint_does_not_trip_epoch_check() -> None:
    result = await _executor([]).run(
        _graph(),
        budget_policy=BudgetPolicy.unlimited(),
        run_id="fresh",
        resume=True,
        envelope=_env(5),
    )
    assert result.status == "ok"


def test_old_checkpoint_without_epoch_reads_as_zero() -> None:
    payload = _graph().checkpoint()
    payload.pop("authorization_epoch")
    assert ExecutionGraph.resume(payload).authorization_epoch == 0


def test_sqlite_store_round_trips_epoch(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ckpt.db"
    clock = mock_datetime_service()
    store = SqliteCheckpointStore(path, datetime_service=clock)
    graph = _graph()
    graph.authorization_epoch = 7
    store.save(graph, run_id="r")
    store.close()
    reopened = SqliteCheckpointStore(path, datetime_service=clock)
    assert reopened.latest_authorization_epoch(run_id="r") == 7
    assert reopened.latest_authorization_epoch(run_id="missing") == 0
    reopened.close()
