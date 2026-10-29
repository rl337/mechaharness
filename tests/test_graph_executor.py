"""Data-driven GraphExecutor matrix + structural unit checks.

Scenario expectations live under ``tests/fixtures/graph_executor/*.json``.
The harness interprets declarative runners/policies so cases are not copy-pastes
of executor control flow.
"""

from __future__ import annotations

from collections import defaultdict

import pytest
from pyiv import get_injector

from mechaharness.budget import Budget, BudgetPolicy
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    DefaultGraphFailurePolicy,
    GraphExecutor,
    GraphFailureAction,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
    RunControl,
    registry_from_mapping,
)
from tests.support.graph_executor_cases import (
    CallLog,
    CaseConfig,
    GraphExecutorCase,
    assert_expect,
    build_escalation,
    build_failure_policy,
    build_graph,
    build_registry,
    iter_cases,
    mutate_graph,
    phases,
    resolve_grants,
)

_CASES = iter_cases()


def _case_id(case: GraphExecutorCase) -> str:
    return case.id


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=_case_id)
async def test_graph_executor_case(case: GraphExecutorCase) -> None:
    data = case.data
    log = CallLog()
    registry = build_registry(data.get("runners"), log)
    config = CaseConfig(
        runners=registry,
        grants=resolve_grants(data.get("grants")),
        failure_policy=build_failure_policy(data.get("failure_policy")),
        escalation=build_escalation(data.get("escalation")),
    )
    executor = get_injector(config).inject(GraphExecutor)
    graph = build_graph(data.get("graph") or {})

    for phase in phases(case):
        start_order = len(log.order)
        start_counts = defaultdict(int, log.by_kind)
        mutate = phase.get("mutate")
        run_spec = phase.get("run") or {}
        if mutate:
            # Apply against the durable checkpoint when resuming.
            if run_spec.get("resume"):
                restored = executor.store.latest(run_id=str(run_spec.get("run_id") or graph.id))
                assert restored is not None, f"{case.id}: missing checkpoint to mutate"
                mutate_graph(restored, mutate)
                executor.store.save(restored, run_id=str(run_spec["run_id"]), boundary="dispatch")
                graph = restored
            else:
                mutate_graph(graph, mutate)

        budget_raw = run_spec.get("budget_policy") or data.get("budget_policy") or {}
        budget_policy = BudgetPolicy(
            soft_limit=budget_raw.get("soft_limit"),
            hard_limit=budget_raw.get("hard_limit"),
            unit=budget_raw.get("unit", "units"),
        )
        control_raw = run_spec.get("control")
        control = (
            RunControl.model_validate(control_raw)
            if isinstance(control_raw, dict)
            else None
        )
        result = await executor.run(
            graph,
            budget_policy=budget_policy,
            run_id=run_spec.get("run_id"),
            resume=bool(run_spec.get("resume")),
            control=control,
        )
        graph = result.graph

        phase_log = CallLog()
        phase_log.order = list(log.order[start_order:])
        for kind, total in log.by_kind.items():
            delta = total - start_counts.get(kind, 0)
            if delta:
                phase_log.by_kind[kind] = delta

        assert_expect(
            result=result,
            expect=phase.get("expect") or {},
            log=phase_log,
            case_id=f"{case.id}:{run_spec.get('run_id', 'phase')}",
        )


@pytest.mark.parametrize(
    ("attempt", "max_attempts", "expected"),
    [
        (0, 3, GraphFailureAction.RETRY),
        (1, 3, GraphFailureAction.RETRY),
        (2, 3, GraphFailureAction.RETRY),
        (3, 3, GraphFailureAction.ESCALATE),
        (4, 3, GraphFailureAction.ESCALATE),
        (1, 1, GraphFailureAction.ESCALATE),
    ],
)
def test_default_failure_policy_matrix(
    attempt: int,
    max_attempts: int,
    expected: GraphFailureAction,
) -> None:
    policy = DefaultGraphFailurePolicy()
    node = GraphNode(id="n", attempt=attempt, max_attempts=max_attempts)
    assert policy.decide(node, error="x") == expected


def test_registry_rejects_duplicate_kind() -> None:
    registry = GraphNodeRunnerRegistry()
    registry.register(CallableGraphNodeRunner(["dup"], lambda n, c: NodeOutcome()))
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(CallableGraphNodeRunner(["dup"], lambda n, c: NodeOutcome()))


def test_callable_runner_requires_kind() -> None:
    with pytest.raises(ValueError, match="at least one kind"):
        CallableGraphNodeRunner([], lambda n, c: NodeOutcome())


@pytest.mark.asyncio
async def test_registry_from_mapping_wires_sync_handler() -> None:
    def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node, context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"sync": True})

    registry = registry_from_mapping({"sync": ok})
    runner = registry.get("sync")
    assert runner is not None
    outcome = await runner.run(
        GraphNode(id="a", kind="sync"),
        context=GraphRunContext(
            graph=ExecutionGraph(),
            run_id="r",
            agent_id="a",
            budget=Budget(BudgetPolicy.unlimited()),
        ),
    )
    assert outcome.payload["sync"] is True


def test_fixture_matrix_is_non_empty() -> None:
    assert len(_CASES) >= 15, "expected a broad static matrix under fixtures/graph_executor"
    ids = [c.id for c in _CASES]
    assert len(ids) == len(set(ids)), f"duplicate case ids: {ids}"


@pytest.mark.asyncio
async def test_walk_bag_survives_checkpoint_across_new_executor() -> None:
    """M1: bag on checkpoint is hydrated when a fresh executor resumes the run."""
    from mechaharness.core.access import GraphExecute
    from mechaharness.di import MechaHarnessConfig
    from mechaharness.harness.base import AbstractHarness
    from mechaharness.harness.pass_through import PassThroughHarness
    from mechaharness.inference.base import InferenceStrategy
    from mechaharness.inference.mock import MockInferenceStrategy
    from mechaharness.walk_bag import WalkBagRegister

    seen: list[object] = []

    async def writer(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node
        context.bag.put(
            WalkBagRegister.ACC,
            {"discovery": {"status": "found"}},
        )
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    async def reader(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node
        seen.append(context.bag.require(WalkBagRegister.ACC))
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return GraphNodeRunnerRegistry(
                [
                    CallableGraphNodeRunner(["write"], writer),
                    CallableGraphNodeRunner(["read"], reader),
                ]
            )

    first = get_injector(Cfg()).inject(GraphExecutor)
    graph = ExecutionGraph(goal="bag")
    graph.add_node(GraphNode(id="w", kind="write"))
    graph.add_node(GraphNode(id="r", kind="read", depends_on=["w"]))
    paused = await first.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="bag-persist",
        control=RunControl(mode="one_step"),
    )
    assert paused.status == "paused"
    assert paused.graph.walk_bag.get("acc") == {"discovery": {"status": "found"}}

    # New executor, same EventLog-backed store via a second inject of the same
    # Config would get a fresh in-memory log — reuse the first store explicitly.
    second = get_injector(Cfg()).inject(GraphExecutor)
    second.store = first.store
    done = await second.run(
        paused.graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="bag-persist",
        resume=True,
        control=RunControl(mode="one_step"),
    )
    assert done.status == "ok"
    assert seen == [{"discovery": {"status": "found"}}]


@pytest.mark.asyncio
async def test_walk_bag_not_shared_across_run_ids() -> None:
    from mechaharness.core.access import GraphExecute
    from mechaharness.di import MechaHarnessConfig
    from mechaharness.harness.base import AbstractHarness
    from mechaharness.harness.pass_through import PassThroughHarness
    from mechaharness.inference.base import InferenceStrategy
    from mechaharness.inference.mock import MockInferenceStrategy
    from mechaharness.walk_bag import WalkBagRegister

    async def writer(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node
        context.bag.put(WalkBagRegister.ACC, {"run": context.run_id})
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return GraphNodeRunnerRegistry(
                [CallableGraphNodeRunner(["write"], writer)]
            )

    executor = get_injector(Cfg()).inject(GraphExecutor)
    g1 = ExecutionGraph(goal="a")
    g1.add_node(GraphNode(id="w", kind="write"))
    r1 = await executor.run(
        g1,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="run-a",
        control=RunControl(mode="one_step"),
    )
    g2 = ExecutionGraph(goal="b")
    g2.add_node(GraphNode(id="w", kind="write"))
    r2 = await executor.run(
        g2,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="run-b",
        control=RunControl(mode="one_step"),
    )
    assert r1.graph.walk_bag["acc"] == {"run": "run-a"}
    assert r2.graph.walk_bag["acc"] == {"run": "run-b"}
    assert executor.store.latest(run_id="run-a").walk_bag["acc"] == {"run": "run-a"}  # type: ignore[index]
    assert executor.store.latest(run_id="run-b").walk_bag["acc"] == {"run": "run-b"}  # type: ignore[index]


@pytest.mark.asyncio
async def test_subgraph_bag_inputs_outputs_no_implicit_share(tmp_path: object) -> None:
    """Child bag is projected; only bag_outputs reach the parent; no aliasing."""
    from pathlib import Path

    from mechaharness.core.access import GraphExecute
    from mechaharness.di import MechaHarnessConfig
    from mechaharness.harness.base import AbstractHarness
    from mechaharness.harness.pass_through import PassThroughHarness
    from mechaharness.inference.base import InferenceStrategy
    from mechaharness.inference.mock import MockInferenceStrategy
    from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore
    from mechaharness.walk_bag import WalkBagRegister
    from pyiv.time import PythonDateTimeService

    seen_child_in: list[object] = []

    async def seed(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node
        context.bag.put(
            WalkBagRegister.ACC,
            {"discovery": {"status": "found", "n": 1}},
        )
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    async def child_work(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node
        inbound = context.bag.require(WalkBagRegister.IN)
        seen_child_in.append(dict(inbound) if isinstance(inbound, dict) else inbound)
        # Mutate nested value — must not leak into parent acc without mapping.
        context.bag.path_put("in.status", "child-mutated")
        context.bag.put(WalkBagRegister.OUT, {"verified": True})
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    async def parent_after(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node
        # Mapped output present; unmapped child mutation must not touch discovery.
        assert context.bag.path_get("acc.discovery.status") == "found"
        assert context.bag.path_get("acc.child_out.verified") is True
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return GraphNodeRunnerRegistry(
                [
                    CallableGraphNodeRunner(["seed"], seed),
                    CallableGraphNodeRunner(["child_work"], child_work),
                    CallableGraphNodeRunner(["after"], parent_after),
                ]
            )

        def get_checkpoint_store(self) -> SqliteCheckpointStore:
            root = Path(str(tmp_path))
            return SqliteCheckpointStore(
                root / "bag-nest.sqlite",
                datetime_service=PythonDateTimeService(),
            )

    executor = get_injector(Cfg()).inject(GraphExecutor)
    child = ExecutionGraph(goal="child")
    child.add_node(GraphNode(id="cw", kind="child_work"))
    parent = ExecutionGraph(goal="parent")
    parent.add_node(GraphNode(id="seed", kind="seed"))
    parent.add_node(
        GraphNode(
            id="nest",
            kind="subgraph",
            depends_on=["seed"],
            subgraph=child.model_dump(mode="json"),
            payload={
                "bag_inputs": {"in": "acc.discovery"},
                "bag_outputs": {"acc.child_out": "out"},
            },
        )
    )
    parent.add_node(GraphNode(id="after", kind="after", depends_on=["nest"]))
    result = await executor.run(
        parent,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="bag-nest",
    )
    assert result.status == "ok"
    assert seen_child_in == [{"status": "found", "n": 1}]
    assert result.graph.walk_bag["acc"]["discovery"]["status"] == "found"
    assert result.graph.walk_bag["acc"]["child_out"] == {"verified": True}

    # SQLite reopen durability for the parent bag after nested merge.
    reopened = get_injector(Cfg()).inject(GraphExecutor)
    restored = reopened.store.latest(run_id="bag-nest")
    assert restored is not None
    assert restored.walk_bag["acc"]["child_out"] == {"verified": True}
