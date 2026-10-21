"""CLI verbs for graph-execution acceptance stories."""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.convergence import ConvergenceContract, ConvergenceGuard
from mechaharness.core.access import (
    AccessPolicy,
    GraphEscalate,
    GraphExecute,
    InMemoryAccessControl,
)
from mechaharness.core.environment import InferenceEnvironment, NoOpInferenceEnvironment
from mechaharness.core.events import InMemoryEventLog
from mechaharness.decision_conflict_checkpoint import (
    neighbor_revisit,
    neighbors_from_write_conflicts,
)
from mechaharness.decision_log import TopologySpan, compute_topology_metrics
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.event_correlators import project_node_attempt_rows
from mechaharness.failure_attribution import (
    attribute_with_repair_target,
    select_rollback_target,
)
from mechaharness.graph import (
    DependencyEdge,
    ExecutionGraph,
    GraphNode,
    NodeStatus,
    VerifierResult,
    bounded_repair,
    qualify_validator,
    validator_qualified,
)
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphEscalation,
    GraphExecutor,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.graph_templates import SubgraphNodeRunner
from mechaharness.graph_transition import (
    GraphTransition,
    TransitionContract,
    inspect_transitions,
)
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.linkage_resolver import DefaultLinkageResolver
from mechaharness.rollout_graph import build_rollout_graph
from mechaharness.tools.base import ToolRegistry
from tests.stories.cli_probes.graph_cost import with_graph_cost


class TopologyEfficiencyCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spans: list[dict[str, Any]] = Field(min_length=1)
    graph_version: str = "1"
    worker_count: int | None = None


class ValidatorQualificationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    good_fixtures: list[str] = Field(default_factory=lambda: ["ok1"])
    bad_fixtures: list[str] = Field(default_factory=lambda: ["bad1"])
    missing_fixtures: list[str] = Field(default_factory=lambda: ["missing"])


class BoundedRepairLoopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = 3
    repaired_path: str = "/tmp/story.png"


class GraphExecutorRunCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = "local pipe"
    produce_value: int = 1
    max_attempts: int = 2
    fail_until_attempt: int = 99
    check_deny: bool = True
    grants: list[str] = Field(
        default_factory=lambda: ["core:graph.execute", "core:graph.escalate"]
    )


class GraphEventCorrelatorsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_id: str
    goal: str
    recipe_id: str
    recipe_version: str
    authorization_epoch: int
    nodes: list[str] = Field(min_length=1)
    run_id: str = "corr-run"


class GraphLinkagePreflightCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_missing_runner: bool = True
    check_missing_stop: bool = True
    check_ok_linear: bool = True


class GraphTransitionInspectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[str] = Field(min_length=1)
    transitions: list[dict[str, Any]] = Field(min_length=1)
    inspect_node: str = "verify"


class TargetedRollbackSelectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str
    node_id: str | None = None
    repair_target: str | None = None
    transitions: list[dict[str, Any]] = Field(default_factory=list)


class RolloutGraphBuildCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[dict[str, Any]] = Field(min_length=1)


class ConvergenceCeilingCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: dict[str, Any]
    fingerprints: list[str] = Field(min_length=1)
    elapsed_ms_per_tick: float = 1.0


def run_topology_efficiency(body: TopologyEfficiencyCommand) -> dict[str, Any]:
    spans = [TopologySpan(**s) for s in body.spans]
    metrics = compute_topology_metrics(
        spans,
        graph_version=body.graph_version,
        worker_count=body.worker_count,
    )
    return {
        "total_node_work_ms": metrics.total_node_work_ms,
        "elapsed_ms": metrics.elapsed_ms,
        "work_exceeds_elapsed": metrics.total_node_work_ms > metrics.elapsed_ms,
        "notes_exactly": list(metrics.notes),
    }


def run_validator_qualification(
    body: ValidatorQualificationCommand,
) -> dict[str, Any]:
    def honest(item: Any) -> VerifierResult:
        if item == "missing":
            return "unknown"
        return "pass" if str(item).startswith("ok") else "fail"

    def always_pass(_item: Any) -> VerifierResult:
        return "pass"

    good = qualify_validator(
        name="honest",
        verifier=honest,
        good_fixtures=body.good_fixtures,
        bad_fixtures=body.bad_fixtures,
        missing_fixtures=body.missing_fixtures,
    )
    weak = qualify_validator(
        name="weak",
        verifier=always_pass,
        good_fixtures=["ok"],
        bad_fixtures=["bad"],
    )
    return {
        "honest_qualified": validator_qualified(good),
        "weak_qualified": validator_qualified(weak),
    }


def run_bounded_repair_loop(body: BoundedRepairLoopCommand) -> dict[str, Any]:
    def has_file(node: GraphNode) -> tuple[bool, dict[str, Any]]:
        ok = bool(node.payload.get("path"))
        return ok, {"file": node.payload.get("path")}

    node = GraphNode(id="repair-story", payload={}, max_attempts=body.max_attempts)
    repaired = bounded_repair(
        node,
        verifiers=[has_file],
        repair=lambda n: n.model_copy(
            update={"payload": {"path": body.repaired_path}}
        ),
    )
    return {"final_status": repaired.status.value}


def _grant_objects(keys: list[str]) -> list[object]:
    known = {
        "core:graph.execute": GraphExecute,
        "core:graph.escalate": GraphEscalate,
    }
    return [known.get(k, k) for k in keys]


async def run_graph_executor_run(body: GraphExecutorRunCommand) -> dict[str, Any]:
    attempts: list[int] = []

    async def produce(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"value": body.produce_value},
            evidence={"node": node.id},
        )

    async def flaky(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        attempts.append(node.attempt)
        if len(attempts) < body.fail_until_attempt:
            return NodeOutcome(status=NodeStatus.FAILED, error="transient")
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"recovered": True})

    async def consume(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node
        parent = context.graph.nodes["produce"]
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"sum": int(parent.payload.get("value", 0)) + 1},
        )

    class _Heal(GraphEscalation):
        async def handle(
            self, node: GraphNode, *, context: GraphRunContext
        ) -> NodeOutcome:
            del context
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={**node.payload, "escalated": True},
            )

    registry = GraphNodeRunnerRegistry(
        [
            CallableGraphNodeRunner(["produce"], produce),
            CallableGraphNodeRunner(["flaky"], flaky),
            CallableGraphNodeRunner(["consume"], consume),
        ]
    )
    grant_objs = _grant_objects(body.grants)

    class StoryGraphConfig(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_harness_config(self) -> HarnessConfig:
            return HarnessConfig(model="story", max_turns=1)

        def get_tools(self) -> ToolRegistry:
            return ToolRegistry()

        def get_grants(self) -> list[object]:
            return list(grant_objs)

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

        def get_graph_escalation(self) -> GraphEscalation:
            return _Heal()

    executor = get_injector(StoryGraphConfig()).inject(GraphExecutor)
    graph = ExecutionGraph(goal=body.goal)
    graph.add_node(GraphNode(id="produce", kind="produce"))
    graph.add_node(
        GraphNode(
            id="flaky",
            kind="flaky",
            depends_on=["produce"],
            max_attempts=body.max_attempts,
        )
    )
    graph.add_node(GraphNode(id="consume", kind="consume", depends_on=["flaky"]))
    graph.add_dependency(
        DependencyEdge(
            from_node="produce",
            to_node="flaky",
            types=["data"],
            reason="flaky needs produce",
        )
    )
    graph.add_dependency(
        DependencyEdge(
            from_node="flaky",
            to_node="consume",
            types=["control"],
            reason="consume after repair",
        )
    )

    denied = None
    if body.check_deny:

        class DenyConfig(StoryGraphConfig):
            def get_grants(self) -> list[object]:
                return []

        denied_exec = get_injector(DenyConfig()).inject(GraphExecutor)
        denied = await denied_exec.run(
            graph.model_copy(deep=True),
            budget_policy=BudgetPolicy.unlimited(),
            run_id="story-deny",
        )

    result = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="story-graph-exec"
    )
    types = [e.type for e in result.events]
    return with_graph_cost(
        {
            "status": result.status,
            "consume_sum": result.graph.nodes["consume"].payload.get("sum"),
            "emitted_graph_start": "core:graph_start" in types,
            "emitted_graph_end": "core:graph_end" in types,
            "denied_without_execute_grant": (
                denied is not None and denied.status == "denied"
            ),
            "flaky_attempts": len(attempts),
        },
        result,
        denied,
    )


async def run_graph_event_correlators(
    body: GraphEventCorrelatorsCommand,
) -> dict[str, Any]:
    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node, context
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
                [CallableGraphNodeRunner(["compute"], ok)]
            )

    executor = get_injector(Cfg()).inject(GraphExecutor)
    child = ExecutionGraph(id="child-graph", goal="nested work")
    child.add_node(GraphNode(id="inner", kind="compute"))
    graph = ExecutionGraph(id=body.graph_id, goal=body.goal)
    graph.template_name = body.recipe_id
    graph.template_version = body.recipe_version
    previous: str | None = None
    for node_id in body.nodes:
        graph.add_node(GraphNode(id=node_id, kind="compute"))
        if previous is not None:
            graph.add_dependency(
                DependencyEdge(
                    from_node=previous,
                    to_node=node_id,
                    types=["data"],
                    reason="story order",
                )
            )
        previous = node_id
    graph.add_node(
        GraphNode(id="nest", kind="subgraph", subgraph=child.model_dump(mode="json"))
    )
    graph.add_dependency(
        DependencyEdge(
            from_node=previous or "",
            to_node="nest",
            types=["data"],
            reason="story order",
        )
    )
    result = await executor.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id=body.run_id,
        envelope=CapabilityEnvelope(
            grants=["core:graph.execute"],
            authorization_epoch=body.authorization_epoch,
        ),
    )
    lifecycle = {
        "core:graph_start",
        "core:graph_end",
        "core:graph_node_start",
        "core:graph_node_end",
    }
    parent_events = [
        e for e in executor.event_log.query(run_id=body.run_id) if e.type in lifecycle
    ]
    child_events = [
        e
        for e in executor.event_log.query(run_id=f"{body.run_id}:nest")
        if e.type in lifecycle
    ]
    node_events = [e for e in parent_events if e.type.startswith("core:graph_node_")]
    rows = project_node_attempt_rows(parent_events)
    recipe_stamps = {
        (e.payload.get("recipe_id"), e.payload.get("recipe_version"))
        for e in parent_events
    }
    return with_graph_cost(
        {
            "status": result.status,
            "graph_events_have_graph_id": all(
                e.payload.get("graph_id") == body.graph_id for e in parent_events
            ),
            "node_events_have_node_id": bool(node_events)
            and all(isinstance(e.payload.get("node_id"), str) for e in node_events),
            "recipe": [list(pair) for pair in sorted(recipe_stamps)],
            "epochs": sorted(
                {e.payload.get("authorization_epoch") for e in parent_events}
            ),
            "child_parent_run_ids": sorted(
                {e.payload.get("parent_run_id") for e in child_events}
            ),
            "child_nest_depths": sorted(
                {e.payload.get("nest_depth") for e in child_events}
            ),
            "node_attempt_rows": [[r.node_id, r.attempt, r.status] for r in rows],
        },
        result,
    )


def run_graph_linkage_preflight(
    body: GraphLinkagePreflightCommand,
) -> dict[str, Any]:
    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    registry = GraphNodeRunnerRegistry(
        [
            CallableGraphNodeRunner(["compute"], ok),
            CallableGraphNodeRunner(["loop"], ok),
        ]
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
    if body.check_missing_runner:
        g = ExecutionGraph(goal="missing")
        g.add_node(GraphNode(id="x", kind="unregistered"))
        report = resolver.resolve(g)
        actual["missing_runner_ok"] = report.ok
        actual["missing_runner_codes_exactly"] = sorted(e.code for e in report.edges)
    if body.check_missing_stop:
        g = ExecutionGraph(goal="loop")
        g.add_node(GraphNode(id="loop", kind="loop", repeating=True))
        report = resolver.resolve(g)
        actual["missing_stop_ok"] = report.ok
        actual["missing_stop_codes_exactly"] = sorted(e.code for e in report.edges)
    if body.check_ok_linear:
        g = ExecutionGraph(goal="ok")
        g.add_node(GraphNode(id="a", kind="compute"))
        g.add_node(GraphNode(id="b", kind="compute", depends_on=["a"]))
        report = resolver.resolve(g)
        actual["ok_linear_ok"] = report.ok
        actual["ok_linear_fingerprint_nonempty"] = bool(report.fingerprint)
    return actual


def run_graph_transition_inspect(
    body: GraphTransitionInspectCommand,
) -> dict[str, Any]:
    contract = TransitionContract(
        transitions=[GraphTransition.model_validate(t) for t in body.transitions]
    )
    kinds = sorted(
        t.kind for t in inspect_transitions(contract, body.inspect_node)
    )
    return {
        "issues": contract.validate_against_nodes(set(body.nodes)),
        "verify_kinds_exactly": kinds,
    }


def run_targeted_rollback_select(
    body: TargetedRollbackSelectCommand,
) -> dict[str, Any]:
    attr = attribute_with_repair_target(
        body.error,
        node_id=body.node_id,
        repair_target=body.repair_target,
    )
    contract = TransitionContract(
        transitions=[GraphTransition.model_validate(t) for t in body.transitions]
    )
    return {
        "rollback_target": select_rollback_target(attr, contract),
        "repair_target": attr.repair_target,
    }


def run_rollout_graph_build(body: RolloutGraphBuildCommand) -> dict[str, Any]:
    graph = build_rollout_graph(body.records)
    retry = graph.nodes.get("retry")
    return {
        "roots_exactly": sorted(graph.roots()),
        "retry_linked": retry is not None and retry.execution_node_id == "produce",
    }


def run_convergence_ceiling(body: ConvergenceCeilingCommand) -> dict[str, Any]:
    contract = ConvergenceContract(**body.contract)
    guard = ConvergenceGuard(contract)
    for fp in body.fingerprints:
        guard.tick(fingerprint=fp, elapsed_ms=float(body.elapsed_ms_per_tick))
    return {
        "terminal": guard.state.terminal,
        "reason": guard.state.reason,
        "success": guard.state.terminal == "success",
    }


class DynamicSubgraphNestCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_goal: str = "parent"
    child_goal: str = "child"


class CheckpointFingerprintRefuseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = "fp"


class EnvironmentLinkageFailCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_grant: str = "core:media.image"


class WakeReresolveResumeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = "wake"


class GraphBudgetLimitsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    soft_policy: dict[str, Any]
    hard_policy: dict[str, Any]
    node_cost: float = 1.0


class GraphBudgetSubgraphRollupCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    soft_limit: float | None = None
    hard_limit: float | None = None
    node_cost: float = 1.0


class DecisionConflictNeighborRevisitCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    start: str
    write_scopes: dict[str, list[str]]
    clears: list[str] = Field(default_factory=list)


def _compute_executor(registry: GraphNodeRunnerRegistry) -> GraphExecutor:
    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    return cast(GraphExecutor, get_injector(Cfg()).inject(GraphExecutor))


async def run_dynamic_subgraph_nest(
    body: DynamicSubgraphNestCommand,
) -> dict[str, Any]:
    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    executor = _compute_executor(
        GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    )
    child = ExecutionGraph(goal=body.child_goal)
    child.add_node(GraphNode(id="c1", kind="compute"))
    parent = ExecutionGraph(goal=body.parent_goal)
    parent.add_node(SubgraphNodeRunner.embed(child, parent_node_id="wrap"))
    result = await executor.run(
        parent,
        budget_policy=BudgetPolicy.unlimited(),
        skip_linkage=True,
        run_id="story-subgraph",
    )
    wrap = result.graph.nodes["wrap"]
    return with_graph_cost(
        {
            "status": result.status,
            "child_status": wrap.payload.get("child_status"),
            "child_run_id_nonempty": bool(wrap.payload.get("child_run_id")),
        },
        result,
    )


async def run_checkpoint_fingerprint_refuse(
    body: CheckpointFingerprintRefuseCommand,
) -> dict[str, Any]:
    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node, context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    executor = _compute_executor(
        GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    )
    graph = ExecutionGraph(goal=body.goal, version="1")
    graph.add_node(GraphNode(id="a", kind="compute"))
    first = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-fp"
    )
    executor.fingerprint_parts = {"harness_version": "changed"}
    resumed = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-fp", resume=True
    )
    err = resumed.error or ""
    return with_graph_cost(
        {
            "first_status": first.status,
            "resume_status": resumed.status,
            "error_code": err.split(":", 1)[0] if err else None,
        },
        first,
        resumed,
    )


def run_environment_linkage_fail(
    body: EnvironmentLinkageFailCommand,
) -> dict[str, Any]:
    class StrictEnv(InferenceEnvironment):
        def active_profile(self) -> str | None:
            return "story-strict"

        def active_capabilities(self) -> Any:
            from mechaharness.core.access import CapabilityProfile

            return CapabilityProfile()

        def active_grants(self) -> list[str]:
            return []

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node, context
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
        envelope=CapabilityEnvelope(grants=[body.required_grant]),
    )
    return {
        "ok": report.ok,
        "codes_exactly": sorted(e.code for e in report.edges),
    }


async def run_wake_reresolve_resume(
    body: WakeReresolveResumeCommand,
) -> dict[str, Any]:
    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node, context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    executor = _compute_executor(
        GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    )
    graph = ExecutionGraph(goal=body.goal)
    graph.add_node(GraphNode(id="a", kind="compute"))
    first = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-wake"
    )
    resolve = executor.linkage_resolver.resolve(first.graph)
    resumed = await executor.run(
        first.graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="insp-wake",
        resume=True,
    )
    return with_graph_cost(
        {
            "resolve_ok": resolve.ok,
            "resume_status": resumed.status,
            "fingerprint_nonempty": bool(
                first.graph.config_fingerprint or resolve.fingerprint
            ),
        },
        first,
        resumed,
    )


async def run_graph_budget_limits(body: GraphBudgetLimitsCommand) -> dict[str, Any]:
    cost = float(body.node_cost)

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"id": node.id},
            cost_units=cost,
        )

    executor = _compute_executor(
        GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    )

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

    soft = await executor.run(
        _linear(),
        budget_policy=BudgetPolicy(
            soft_limit=body.soft_policy.get("soft_limit"),
            hard_limit=body.soft_policy.get("hard_limit"),
        ),
        run_id="story-budget-soft",
    )
    hard = await executor.run(
        _linear(),
        budget_policy=BudgetPolicy(
            soft_limit=body.hard_policy.get("soft_limit"),
            hard_limit=body.hard_policy.get("hard_limit"),
        ),
        run_id="story-budget-hard",
    )
    return with_graph_cost(
        {
            "soft_status": soft.status,
            "soft_error": soft.error,
            "soft_budget_level": soft.budget_level,
            "hard_status": hard.status,
            "hard_error": hard.error,
            "hard_budget_level": hard.budget_level,
        },
        soft,
        hard,
    )


async def run_graph_budget_subgraph_rollup(
    body: GraphBudgetSubgraphRollupCommand,
) -> dict[str, Any]:
    cost = float(body.node_cost)

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"id": node.id},
            cost_units=cost,
        )

    executor = _compute_executor(
        GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    )
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
    result = await executor.run(
        parent,
        budget_policy=BudgetPolicy(
            soft_limit=body.soft_limit, hard_limit=body.hard_limit
        ),
        skip_linkage=True,
        run_id="story-budget-rollup",
    )
    return with_graph_cost(
        {
            "status": result.status,
            "budget_spent": result.budget_spent,
            "budget_level": result.budget_level,
            "error": result.error,
            "after_status": parent.nodes["after"].status.value,
        },
        result,
    )


def run_decision_conflict_neighbor_revisit(
    body: DecisionConflictNeighborRevisitCommand,
) -> dict[str, Any]:
    graph = ExecutionGraph(goal=body.id)
    for node_id, scopes in body.write_scopes.items():
        graph.add_node(GraphNode(id=node_id, kind="decide", write_scopes=scopes))
    conflicts = graph.concurrent_write_conflicts(list(body.write_scopes))
    cleared = set(body.clears)
    visited: set[str] = set()
    queue = [body.start]
    order: list[str] = []
    checkpoints: list[str] = []
    cycle_blocked: list[str] = []
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        order.append(node)
        neighbors = (
            [] if node in cleared else neighbors_from_write_conflicts(node, conflicts)
        )
        step = neighbor_revisit(node, neighbors, visited=visited)
        visited = set(step.visited)
        queue.extend(step.revisit)
        if step.checkpoint:
            checkpoints.append(node)
        if step.cycle_blocked:
            cycle_blocked.append(node)
    return {
        "order": order,
        "checkpoints": checkpoints,
        "cycle_blocked": cycle_blocked,
    }


__all__ = [
    "BoundedRepairLoopCommand",
    "CheckpointFingerprintRefuseCommand",
    "ConvergenceCeilingCommand",
    "DecisionConflictNeighborRevisitCommand",
    "DynamicSubgraphNestCommand",
    "EnvironmentLinkageFailCommand",
    "GraphBudgetLimitsCommand",
    "GraphBudgetSubgraphRollupCommand",
    "GraphEventCorrelatorsCommand",
    "GraphExecutorRunCommand",
    "GraphLinkagePreflightCommand",
    "GraphTransitionInspectCommand",
    "RolloutGraphBuildCommand",
    "TargetedRollbackSelectCommand",
    "TopologyEfficiencyCommand",
    "ValidatorQualificationCommand",
    "WakeReresolveResumeCommand",
    "run_bounded_repair_loop",
    "run_checkpoint_fingerprint_refuse",
    "run_convergence_ceiling",
    "run_decision_conflict_neighbor_revisit",
    "run_dynamic_subgraph_nest",
    "run_environment_linkage_fail",
    "run_graph_budget_limits",
    "run_graph_budget_subgraph_rollup",
    "run_graph_event_correlators",
    "run_graph_executor_run",
    "run_graph_linkage_preflight",
    "run_graph_transition_inspect",
    "run_rollout_graph_build",
    "run_targeted_rollback_select",
    "run_topology_efficiency",
    "run_validator_qualification",
    "run_wake_reresolve_resume",
]
