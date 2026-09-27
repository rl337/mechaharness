"""Data-driven GraphExecutor matrix + structural unit checks.

Scenario expectations live under ``tests/fixtures/graph_executor/*.json``.
The harness interprets declarative runners/policies so cases are not copy-pastes
of executor control flow.
"""

from __future__ import annotations

from collections import defaultdict

import pytest
from pyiv import get_injector

from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    DefaultGraphFailurePolicy,
    GraphExecutor,
    GraphFailureAction,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
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

        result = await executor.run(
            graph,
            run_id=run_spec.get("run_id"),
            resume=bool(run_spec.get("resume")),
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
        ),
    )
    assert outcome.payload["sync"] is True


def test_fixture_matrix_is_non_empty() -> None:
    assert len(_CASES) >= 15, "expected a broad static matrix under fixtures/graph_executor"
    ids = [c.id for c in _CASES]
    assert len(ids) == len(set(ids)), f"duplicate case ids: {ids}"
