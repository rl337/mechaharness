"""Graph executor, checkpoint/resume, budget, and linkage story runners."""

from __future__ import annotations

from typing import Any

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.convergence import ConvergenceContract, ConvergenceGuard
from mechaharness.core.access import (
    AccessPolicy,
    GraphExecute,
    InMemoryAccessControl,
)
from mechaharness.core.environment import (
    InferenceEnvironment,
    NoOpInferenceEnvironment,
)
from mechaharness.core.events import InMemoryEventLog
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.failure_attribution import (
    attribute_with_repair_target,
    select_rollback_target,
)
from mechaharness.graph import (
    DependencyEdge,
    ExecutionGraph,
    FanInItem,
    GraphNode,
    GraphStore,
    NodeStatus,
    hierarchical_fan_in,
    merge_branch_artifacts,
)
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphExecutor,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.graph_templates import (
    SubgraphNodeRunner,
)
from mechaharness.graph_transition import GraphTransition, TransitionContract, inspect_transitions
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.linkage_resolver import DefaultLinkageResolver
from mechaharness.operation_registry import (
    NodeContractBind,
    OperationContract,
    ResourceScope,
    default_operations,
)
from mechaharness.rollout_graph import build_rollout_graph
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import StoryRunner, _assert_expect, _story_graph_executor


async def _run_convergence_ceiling(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    contract = ConvergenceContract(**request["contract"])
    guard = ConvergenceGuard(contract)
    fingerprints = list(request.get("fingerprints", []))
    for fp in fingerprints:
        guard.tick(fingerprint=fp, elapsed_ms=float(request.get("elapsed_ms_per_tick", 1)))
    actual = {
        "terminal_in": guard.state.terminal,
        "reason_in": guard.state.reason,
        "success": guard.state.terminal == "success",
    }
    _assert_expect(actual, expect)


async def _run_local_plan_resume(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    ops = default_operations()
    ops.register(
        "write_file",
        lambda **_: None,
        contract=OperationContract(
            name="write_file",
            version="1",
            write_scopes=[ResourceScope(name="app.py", mode="write")],
            preconditions=["approved"],
            external_effects="write",
        ),
    )
    bind = NodeContractBind(
        operation="write_file",
        contract_version="1",
        state_revision=request.get("state_revision", "r1"),
        planned_effects="write",
        evidence_refs=request.get("evidence_refs", []),
    )
    ops.bind_node(bind)
    stale = ops.recheck_preconditions("write_file", satisfied=request.get("satisfied", []))

    graph = ExecutionGraph(goal=request.get("goal", "ship patch"))
    graph.add_node(
        GraphNode(
            id="produce",
            status=NodeStatus.SUCCEEDED,
            write_scopes=["app.py"],
            payload={"path": "app.py", "content": "v1"},
        )
    )
    graph.add_node(
        GraphNode(
            id="consume",
            write_scopes=["app.py"],
            status=NodeStatus.PENDING,
        )
    )
    graph.add_dependency(
        DependencyEdge(
            from_node="produce",
            to_node="consume",
            types=["data", "resource"],
            reason="consume needs produce output; exclusive write",
            evidence_ref="edge:1",
        )
    )
    store = GraphStore(InMemoryEventLog())
    store.save(graph, run_id="story-graph", boundary="dispatch")
    restored = store.latest(run_id="story-graph")
    assert restored is not None
    ready = [n.id for n in restored.ready_nodes()]
    fan = hierarchical_fan_in(
        [
            FanInItem(id="ok", source_ref="b1", payload={"id": "x"}),
            FanInItem(id="dup", source_ref="b2", payload={"id": "x"}),
            FanInItem(id="bad", source_ref="b3", payload={"id": "y"}, failed=True),
        ],
        budget=int(request.get("fan_in_budget", 4)),
    )
    merged = merge_branch_artifacts(
        base_revision="r0",
        branches=request.get(
            "branches",
            [
                {"path": "app.py", "content": "a", "status": "ok"},
                {"path": "app.py", "content": "b", "status": "ok"},
            ],
        ),
    )
    actual = {
        "stale_preconditions_include": stale,
        "ready_include": ready,
        "dependency_justified": all(e.reason and e.types for e in restored.edges),
        "fan_in_failures_include": fan.failures,
        "merge_conflicts_include": merged["conflicts"],
        "recovery_boundary_in": store.latest_boundary(run_id="story-graph"),
    }
    _assert_expect(actual, expect)


async def _run_graph_linkage_preflight(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    registry = GraphNodeRunnerRegistry(
        [CallableGraphNodeRunner(["compute"], ok), CallableGraphNodeRunner(["loop"], ok)]
    )
    access = InMemoryAccessControl(
        event_log=InMemoryEventLog(),
        policy=AccessPolicy(grants=[GraphExecute]),
    )
    resolver = DefaultLinkageResolver(
        runners=registry,
        access=access,
        environment=NoOpInferenceEnvironment(),
    )

    actual: dict[str, Any] = {}
    if request.get("check_missing_runner", True):
        g = ExecutionGraph(goal="missing")
        g.add_node(GraphNode(id="x", kind="unregistered"))
        report = resolver.resolve(g)
        actual["missing_runner_ok"] = report.ok
        actual["missing_runner_codes_include"] = [e.code for e in report.edges]
    if request.get("check_missing_stop", True):
        g = ExecutionGraph(goal="loop")
        g.add_node(GraphNode(id="loop", kind="loop", repeating=True))
        report = resolver.resolve(g)
        actual["missing_stop_ok"] = report.ok
        actual["missing_stop_codes_include"] = [e.code for e in report.edges]
    if request.get("check_ok_linear", True):
        g = ExecutionGraph(goal="ok")
        g.add_node(GraphNode(id="a", kind="compute"))
        g.add_node(GraphNode(id="b", kind="compute", depends_on=["a"]))
        report = resolver.resolve(g)
        actual["ok_linear_ok"] = report.ok
        actual["ok_linear_fingerprint_nonempty"] = bool(report.fingerprint)
    _assert_expect(actual, expect)


async def _run_dynamic_subgraph_nest(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    executor = get_injector(Cfg()).inject(GraphExecutor)
    child = ExecutionGraph(goal=str(request.get("child_goal") or "child"))
    child.add_node(GraphNode(id="c1", kind="compute"))
    parent = ExecutionGraph(goal=str(request.get("parent_goal") or "parent"))
    parent.add_node(SubgraphNodeRunner.embed(child, parent_node_id="wrap"))
    result = await executor.run(
        parent,
        budget_policy=BudgetPolicy.unlimited(),
        skip_linkage=True,
        run_id="story-subgraph",
    )
    wrap = result.graph.nodes["wrap"]
    actual = {
        "status": result.status,
        "child_status": wrap.payload.get("child_status"),
        "child_run_id_nonempty": bool(wrap.payload.get("child_run_id")),
    }
    _assert_expect(actual, expect)


async def _run_checkpoint_fingerprint_refuse(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    executor = get_injector(Cfg()).inject(GraphExecutor)
    graph = ExecutionGraph(goal=str(request.get("goal") or "fp"), version="1")
    graph.add_node(GraphNode(id="a", kind="compute"))
    first = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-fp"
    )
    executor.fingerprint_parts = {"harness_version": "changed"}
    resumed = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-fp", resume=True
    )
    actual = {
        "first_status": first.status,
        "resume_status": resumed.status,
        "error_contains": resumed.error or "",
    }
    _assert_expect(actual, expect)


async def _run_environment_linkage_fail(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    class StrictEnv(InferenceEnvironment):
        def active_profile(self) -> str | None:
            return "story-strict"

        def active_capabilities(self):
            from mechaharness.core.access import CapabilityProfile

            return CapabilityProfile()

        def active_grants(self) -> list[str]:
            return []

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    access = InMemoryAccessControl(
        event_log=InMemoryEventLog(),
        policy=AccessPolicy(grants=[GraphExecute]),
    )

    resolver = DefaultLinkageResolver(
        runners=registry,
        access=access,
        environment=StrictEnv(),
    )
    graph = ExecutionGraph(goal="env")
    graph.add_node(GraphNode(id="a", kind="compute"))
    report = resolver.resolve(
        graph,
        envelope=CapabilityEnvelope(grants=[str(request.get("required_grant"))]),
    )
    actual = {
        "ok": report.ok,
        "codes_include": [e.code for e in report.edges],
    }
    _assert_expect(actual, expect)


async def _run_wake_reresolve_resume(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    inj = get_injector(Cfg())
    executor = inj.inject(GraphExecutor)
    graph = ExecutionGraph(goal=str(request.get("goal") or "wake"))
    graph.add_node(GraphNode(id="a", kind="compute"))
    # Client wake: resolve then run; checkpoint; wake again with matching fingerprint
    first = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-wake"
    )
    resolve = executor.linkage_resolver.resolve(first.graph)
    resumed = await executor.run(
        first.graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-wake", resume=True
    )
    actual = {
        "resolve_ok": resolve.ok,
        "resume_status": resumed.status,
        "fingerprint_nonempty": bool(first.graph.config_fingerprint or resolve.fingerprint),
    }
    _assert_expect(actual, expect)


async def _run_graph_budget_limits(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    cost = float(request.get("node_cost", 1))

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"id": node.id},
            cost_units=cost,
        )

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    executor = _story_graph_executor(registry)

    def _linear() -> ExecutionGraph:
        g = ExecutionGraph(goal="budget-limits")
        g.add_node(GraphNode(id="a", kind="compute", payload={"cost_units": cost}))
        g.add_node(
            GraphNode(
                id="b",
                kind="compute",
                depends_on=["a"],
                payload={"cost_units": cost},
            )
        )
        return g

    soft_pol = BudgetPolicy(
        soft_limit=request["soft_policy"].get("soft_limit"),
        hard_limit=request["soft_policy"].get("hard_limit"),
    )
    soft = await executor.run(_linear(), budget_policy=soft_pol, run_id="story-budget-soft")
    hard_pol = BudgetPolicy(
        soft_limit=request["hard_policy"].get("soft_limit"),
        hard_limit=request["hard_policy"].get("hard_limit"),
    )
    hard = await executor.run(_linear(), budget_policy=hard_pol, run_id="story-budget-hard")
    actual = {
        "soft_status": soft.status,
        "soft_error": soft.error,
        "soft_budget_level": soft.budget_level,
        "hard_status": hard.status,
        "hard_error": hard.error,
        "hard_budget_level": hard.budget_level,
    }
    _assert_expect(actual, expect)


async def _run_graph_budget_subgraph_rollup(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    cost = float(request.get("node_cost", 1))

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"id": node.id},
            cost_units=cost,
        )

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    executor = _story_graph_executor(registry)

    child = ExecutionGraph(goal="child-budget")
    child.add_node(GraphNode(id="c1", kind="compute", payload={"cost_units": cost}))
    child.add_node(
        GraphNode(
            id="c2",
            kind="compute",
            depends_on=["c1"],
            payload={"cost_units": cost},
        )
    )
    parent = ExecutionGraph(goal="parent-budget")
    parent.add_node(SubgraphNodeRunner.embed(child, parent_node_id="wrap"))
    parent.add_node(
        GraphNode(
            id="after",
            kind="compute",
            depends_on=["wrap"],
            payload={"cost_units": cost},
        )
    )
    policy = BudgetPolicy(
        soft_limit=request.get("soft_limit"),
        hard_limit=request.get("hard_limit"),
    )
    result = await executor.run(
        parent,
        budget_policy=policy,
        skip_linkage=True,
        run_id="story-budget-rollup",
    )
    actual = {
        "status": result.status,
        "budget_spent": result.budget_spent,
        "budget_level": result.budget_level,
        "error": result.error,
        "after_status": parent.nodes["after"].status.value,
    }
    _assert_expect(actual, expect)


async def _run_transactional_durable_resume_crash_matrix(
    case: StoryCase, backend: StoryBackend
) -> None:
    """DR-12: Downstream-client-shaped fake coding-job crash matrix against SQLite."""
    del backend
    import tempfile
    from pathlib import Path

    from tests.support.transactional_durable_resume_cases import (
        TransactionalDurableResumeCase,
        assert_expect,
        run_crash_case,
    )

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    cases_expect = dict(expect.get("cases") or {})
    locations = list(request.get("crash_locations") or [])
    assert locations, "request.json must list crash_locations"

    with tempfile.TemporaryDirectory(prefix="mh-tdr-story-") as tmp:
        for location in locations:
            case_expect = dict(cases_expect.get(location) or {})
            fixture = TransactionalDurableResumeCase(
                path=Path(f"{location}.json"),
                data={
                    "id": location,
                    "crash_location": location,
                    "run_id": f"{request.get('run_id_prefix', 'story-tdr')}-{location}",
                    "goal": request.get("goal") or "downstream-coding-job",
                    "expect": case_expect,
                },
            )
            db = Path(tmp) / f"{location}.sqlite"
            payload = await run_crash_case(fixture, db_path=db)
            assert_expect(payload["actual"], case_expect)


async def _run_graph_transition_inspect(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    contract = TransitionContract(
        transitions=[GraphTransition.model_validate(t) for t in request.get("transitions") or []]
    )
    nodes = set(request.get("nodes") or [])
    kinds = [t.kind for t in inspect_transitions(contract, "verify")]
    actual = {
        "issues": contract.validate_against_nodes(nodes),
        "verify_kinds_include": kinds,
    }
    _assert_expect(actual, expect)


async def _run_targeted_rollback_select(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    attr = attribute_with_repair_target(
        str(request.get("error") or ""),
        node_id=request.get("node_id"),
        repair_target=request.get("repair_target"),
    )
    contract = TransitionContract(
        transitions=[GraphTransition.model_validate(t) for t in request.get("transitions") or []]
    )
    actual = {
        "rollback_target": select_rollback_target(attr, contract),
        "repair_target": attr.repair_target,
    }
    _assert_expect(actual, expect)


async def _run_rollout_graph_build(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    graph = build_rollout_graph(request.get("records") or [])
    actual = {
        "roots_include": graph.roots(),
        "retry_linked": graph.nodes.get("retry") is not None
        and graph.nodes["retry"].execution_node_id == "produce",
    }
    _assert_expect(actual, expect)


async def _run_decision_conflict_neighbor_revisit(
    case: StoryCase, backend: StoryBackend
) -> None:
    """Neighbor revisit with cycle prevention over write-scope conflicts (MH-SR-08)."""
    del backend
    from mechaharness.decision_conflict_checkpoint import (
        neighbor_revisit,
        neighbors_from_write_conflicts,
    )

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    results: dict[str, Any] = {}
    for scenario in request["scenarios"]:
        graph = ExecutionGraph(goal=scenario["id"])
        for node_id, scopes in scenario["write_scopes"].items():
            graph.add_node(GraphNode(id=node_id, kind="decide", write_scopes=scopes))
        conflicts = graph.concurrent_write_conflicts(list(scenario["write_scopes"]))
        cleared = set(scenario.get("clears", []))
        visited: set[str] = set()
        queue = [scenario["start"]]
        order: list[str] = []
        checkpoints: list[str] = []
        cycle_blocked: list[str] = []
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            order.append(node)
            neighbors = [] if node in cleared else neighbors_from_write_conflicts(node, conflicts)
            step = neighbor_revisit(node, neighbors, visited=visited)
            visited = set(step.visited)
            queue.extend(step.revisit)
            if step.checkpoint:
                checkpoints.append(node)
            if step.cycle_blocked:
                cycle_blocked.append(node)
        results[scenario["id"]] = {
            "order": order,
            "checkpoints": checkpoints,
            "cycle_blocked": cycle_blocked,
        }
    _assert_expect({"scenarios": results}, expect)



RUNNERS: dict[str, StoryRunner] = {
    "convergence_ceiling": _run_convergence_ceiling,
    "local_plan_resume": _run_local_plan_resume,
    "graph_linkage_preflight": _run_graph_linkage_preflight,
    "dynamic_subgraph_nest": _run_dynamic_subgraph_nest,
    "checkpoint_fingerprint_refuse": _run_checkpoint_fingerprint_refuse,
    "environment_linkage_fail": _run_environment_linkage_fail,
    "wake_reresolve_resume": _run_wake_reresolve_resume,
    "graph_budget_limits": _run_graph_budget_limits,
    "graph_budget_subgraph_rollup": _run_graph_budget_subgraph_rollup,
    "transactional_durable_resume_crash_matrix": _run_transactional_durable_resume_crash_matrix,
    "graph_transition_inspect": _run_graph_transition_inspect,
    "targeted_rollback_select": _run_targeted_rollback_select,
    "rollout_graph_build": _run_rollout_graph_build,
    "decision_conflict_neighbor_revisit": _run_decision_conflict_neighbor_revisit,
}
