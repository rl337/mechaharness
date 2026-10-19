"""CLI verbs for graph-execution acceptance stories."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import GraphEscalate, GraphExecute
from mechaharness.decision_log import TopologySpan, compute_topology_metrics
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.event_correlators import project_node_attempt_rows
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
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.tools.base import ToolRegistry


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
    return {
        "status": result.status,
        "consume_sum": result.graph.nodes["consume"].payload.get("sum"),
        "emitted_graph_start": "core:graph_start" in types,
        "emitted_graph_end": "core:graph_end" in types,
        "denied_without_execute_grant": denied is not None and denied.status == "denied",
        "flaky_attempts": len(attempts),
    }


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
    return {
        "status": result.status,
        "graph_events_have_graph_id": all(
            e.payload.get("graph_id") == body.graph_id for e in parent_events
        ),
        "node_events_have_node_id": bool(node_events)
        and all(isinstance(e.payload.get("node_id"), str) for e in node_events),
        "recipe": [list(pair) for pair in sorted(recipe_stamps)],
        "epochs": sorted({e.payload.get("authorization_epoch") for e in parent_events}),
        "child_parent_run_ids": sorted(
            {e.payload.get("parent_run_id") for e in child_events}
        ),
        "child_nest_depths": sorted(
            {e.payload.get("nest_depth") for e in child_events}
        ),
        "node_attempt_rows": [[r.node_id, r.attempt, r.status] for r in rows],
    }


__all__ = [
    "BoundedRepairLoopCommand",
    "GraphEventCorrelatorsCommand",
    "GraphExecutorRunCommand",
    "TopologyEfficiencyCommand",
    "ValidatorQualificationCommand",
    "run_bounded_repair_loop",
    "run_graph_event_correlators",
    "run_graph_executor_run",
    "run_topology_efficiency",
    "run_validator_qualification",
]
