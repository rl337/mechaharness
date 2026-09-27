"""Injectable execution-graph runner (schedule, authorize, retry, escalate).

Hosts define node behavior as :class:`GraphNodeRunner` injectables and bind a
:class:`GraphNodeRunnerRegistry` via Config. The executor walks
:class:`~mechaharness.graph.ExecutionGraph` ready nodes, enforces grants,
emits lifecycle events, checkpoints through :class:`~mechaharness.graph.GraphStore`,
and applies a :class:`GraphFailurePolicy` / :class:`GraphEscalation` on failure.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.access import (
    AccessControl,
    GraphEscalate,
    GraphExecute,
    grant_key,
)
from mechaharness.core.events import (
    Event,
    EventLog,
    EventType,
    GraphEnd,
    GraphNodeEnd,
    GraphNodeStart,
    GraphStart,
    event_type_key,
)
from mechaharness.core.exceptions import GraphExecutorError
from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
    GraphStore,
    NodeStatus,
)


class GraphFailureAction(str, Enum):
    """What to do after a node attempt fails verification or raises."""

    RETRY = "retry"
    ESCALATE = "escalate"
    FAIL = "fail"


class NodeOutcome(BaseModel):
    """Result of one runner attempt against a node."""

    model_config = ConfigDict(extra="allow")

    status: NodeStatus = NodeStatus.SUCCEEDED
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class GraphRunContext:
    """Per-run identity passed to node runners and escalation."""

    graph: ExecutionGraph
    run_id: str
    agent_id: str
    parent_agent_id: str | None = None


class GraphResult(BaseModel):
    """Outcome of :meth:`GraphExecutor.run`."""

    model_config = ConfigDict(extra="allow")

    status: Literal["ok", "failed", "denied", "stalled"]
    graph: ExecutionGraph
    run_id: str
    events: list[Event] = Field(default_factory=list)
    error: str | None = None


NodeHandler = Callable[
    [GraphNode, GraphRunContext],
    Union[Awaitable[NodeOutcome], NodeOutcome],
]


class GraphNodeRunner(ABC):
    """Host-supplied handler for one or more ``GraphNode.kind`` values."""

    @abstractmethod
    def kinds(self) -> Sequence[str]:
        """Node kinds this runner accepts (open string identity)."""

    def required_grants(self) -> Sequence[object]:
        """Extra grants checked before each node this runner handles."""
        return ()

    @abstractmethod
    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        """Execute ``node`` once; return success or failure outcome."""


class CallableGraphNodeRunner(GraphNodeRunner):
    """Adapter: bind a callable (sync or async) to one or more kinds."""

    def __init__(
        self,
        kinds: Sequence[str],
        handler: NodeHandler,
        *,
        grants: Sequence[object] | None = None,
    ) -> None:
        if not kinds:
            raise ValueError("CallableGraphNodeRunner requires at least one kind")
        self._kinds = list(kinds)
        self._handler = handler
        self._grants = [grant_key(item) for item in (grants or [])]

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return list(self._grants)

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        result = self._handler(node, context)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, NodeOutcome):
            raise TypeError(f"node handler must return NodeOutcome, got {type(result)!r}")
        return result


class GraphNodeRunnerRegistry:
    """Map of node kind → runner. Hosts populate via Config hooks."""

    def __init__(self, runners: Sequence[GraphNodeRunner] | None = None) -> None:
        self._by_kind: dict[str, GraphNodeRunner] = {}
        for runner in runners or []:
            self.register(runner)

    def register(self, runner: GraphNodeRunner) -> None:
        for kind in runner.kinds():
            if not kind:
                raise ValueError("node kind must be non-empty")
            existing = self._by_kind.get(kind)
            if existing is not None and existing is not runner:
                raise ValueError(f"duplicate graph node runner for kind {kind!r}")
            self._by_kind[kind] = runner

    def get(self, kind: str) -> GraphNodeRunner | None:
        return self._by_kind.get(kind)

    def kinds(self) -> list[str]:
        return sorted(self._by_kind)


class GraphFailurePolicy(ABC):
    """Decide retry / escalate / fail after a failed node attempt."""

    @abstractmethod
    def decide(self, node: GraphNode, *, error: str | None) -> GraphFailureAction:
        """Return the next action for ``node`` after a failed attempt."""


class DefaultGraphFailurePolicy(GraphFailurePolicy):
    """Retry while attempts remain; then escalate; callers may still FAIL."""

    def decide(self, node: GraphNode, *, error: str | None) -> GraphFailureAction:
        del error
        if node.attempt < node.max_attempts:
            return GraphFailureAction.RETRY
        return GraphFailureAction.ESCALATE


class GraphEscalation(ABC):
    """Host hook when failure policy chooses escalate."""

    @abstractmethod
    async def handle(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        """Attempt recovery or mark the node terminal."""


class RejectGraphEscalation(GraphEscalation):
    """Default: escalation is unavailable; leave the node failed."""

    async def handle(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.FAILED,
            payload=dict(node.payload),
            evidence=dict(node.evidence),
            error=node.error or "escalation_rejected",
        )


class GraphExecutor:
    """Authorize and walk an :class:`~mechaharness.graph.ExecutionGraph`.

    Constructor dependencies are pyiv-injectable. Hosts subclass Config and
    override ``get_node_runner_registry`` / ``get_graph_failure_policy`` /
    ``get_graph_escalation`` rather than hand-building the executor.
    """

    def __init__(
        self,
        event_log: EventLog,
        access: AccessControl,
        runners: GraphNodeRunnerRegistry,
        failure_policy: GraphFailurePolicy,
        escalation: GraphEscalation,
        *,
        agent_id: str | None = None,
        parent_agent_id: str | None = None,
    ) -> None:
        self.event_log = event_log
        self.access = access
        self.runners = runners
        self.failure_policy = failure_policy
        self.escalation = escalation
        self.agent_id = agent_id or str(uuid4())
        self.parent_agent_id = parent_agent_id
        self.store = GraphStore(event_log, agent_id=self.agent_id)

    def _emit(self, event_type: type[EventType], payload: dict[str, Any], run_id: str) -> None:
        self.event_log.emit(
            Event(
                type=event_type_key(event_type),
                agent_id=self.agent_id,
                parent_agent_id=self.parent_agent_id,
                run_id=run_id,
                payload=payload,
            )
        )

    def _allows(
        self,
        required: Sequence[object],
        *,
        tool_name: str,
        run_id: str,
    ) -> bool:
        return self.access.allows(
            required,
            tool_name=tool_name,
            agent_id=self.agent_id,
            run_id=run_id,
            parent_agent_id=self.parent_agent_id,
        )

    def _apply_outcome(self, node: GraphNode, outcome: NodeOutcome) -> None:
        if outcome.payload:
            node.payload = {**node.payload, **outcome.payload}
        if outcome.evidence:
            node.evidence = {**node.evidence, **outcome.evidence}
        node.error = outcome.error
        node.status = outcome.status

    def _terminal_status(self, graph: ExecutionGraph) -> Literal["ok", "failed", "stalled"]:
        statuses = {n.status for n in graph.nodes.values()}
        if statuses and statuses <= {NodeStatus.SUCCEEDED}:
            return "ok"
        if any(n.status == NodeStatus.FAILED for n in graph.nodes.values()):
            if not graph.ready_nodes():
                return "failed"
        if graph.ready_nodes():
            return "stalled"
        active = {
            NodeStatus.PENDING,
            NodeStatus.READY,
            NodeStatus.BLOCKED,
            NodeStatus.RUNNING,
        }
        if any(n.status in active for n in graph.nodes.values()):
            return "stalled"
        return "failed"

    async def run(
        self,
        graph: ExecutionGraph,
        *,
        run_id: str | None = None,
        resume: bool = False,
    ) -> GraphResult:
        """Execute ``graph`` until completion, denial, stall, or hard failure.

        When ``resume`` is true, load the latest checkpoint for ``run_id`` (or
        ``graph.id``) and continue from that snapshot.
        """
        rid = run_id or graph.id
        if resume:
            restored = self.store.latest(run_id=rid)
            if restored is not None:
                graph = restored

        if not self._allows([GraphExecute], tool_name="graph_executor", run_id=rid):
            self._emit(
                GraphStart,
                {"goal": graph.goal, "node_count": len(graph.nodes), "status": "denied"},
                rid,
            )
            self._emit(
                GraphEnd,
                {"status": "denied", "error": "missing_grant:core:graph.execute"},
                rid,
            )
            return GraphResult(
                status="denied",
                graph=graph,
                run_id=rid,
                events=self.event_log.query(run_id=rid),
                error="missing_grant:core:graph.execute",
            )

        context = GraphRunContext(
            graph=graph,
            run_id=rid,
            agent_id=self.agent_id,
            parent_agent_id=self.parent_agent_id,
        )
        self._emit(
            GraphStart,
            {
                "goal": graph.goal,
                "node_count": len(graph.nodes),
                "kinds": self.runners.kinds(),
            },
            rid,
        )
        self.store.save(graph, run_id=rid, boundary="dispatch")

        try:
            await self._run_loop(graph, context)
        except GraphExecutorError as exc:
            self.store.save(graph, run_id=rid, boundary="commit")
            status = self._terminal_status(graph)
            self._emit(GraphEnd, {"status": status, "error": str(exc)}, rid)
            return GraphResult(
                status=status if status != "ok" else "failed",
                graph=graph,
                run_id=rid,
                events=self.event_log.query(run_id=rid),
                error=str(exc),
            )

        self.store.save(graph, run_id=rid, boundary="commit")
        status = self._terminal_status(graph)
        self._emit(GraphEnd, {"status": status, "node_count": len(graph.nodes)}, rid)
        return GraphResult(
            status=status,
            graph=graph,
            run_id=rid,
            events=self.event_log.query(run_id=rid),
            error=None if status == "ok" else "graph_incomplete",
        )

    async def _run_loop(self, graph: ExecutionGraph, context: GraphRunContext) -> None:
        # Bound iterations: each node may attempt up to max_attempts (+ escalation).
        budget = sum(max(1, n.max_attempts) for n in graph.nodes.values()) + len(graph.nodes) + 1
        for _ in range(budget):
            ready = graph.ready_nodes()
            if not ready:
                return
            conflicts = graph.concurrent_write_conflicts([n.id for n in ready])
            if conflicts and len(ready) > 1:
                # Sequential safety: pick one non-conflicting node; if all conflict, run first.
                ready = [ready[0]]
            node = ready[0]
            await self._run_node(graph, node, context)
            self.store.save(graph, run_id=context.run_id, boundary="reduce")
        raise GraphExecutorError("exceeded graph execution budget")

    async def _run_node(
        self,
        graph: ExecutionGraph,
        node: GraphNode,
        context: GraphRunContext,
    ) -> None:
        del graph
        runner = self.runners.get(node.kind)
        if runner is None:
            node.status = NodeStatus.FAILED
            node.error = f"no_runner:{node.kind}"
            node.attempt += 1
            self._emit(
                GraphNodeEnd,
                {
                    "node_id": node.id,
                    "kind": node.kind,
                    "status": node.status.value,
                    "error": node.error,
                },
                context.run_id,
            )
            return

        grants = list(runner.required_grants())
        if grants and not self._allows(
            grants,
            tool_name=f"graph_node:{node.kind}",
            run_id=context.run_id,
        ):
            node.status = NodeStatus.FAILED
            node.error = "permission_denied"
            node.attempt += 1
            self._emit(
                GraphNodeEnd,
                {
                    "node_id": node.id,
                    "kind": node.kind,
                    "status": node.status.value,
                    "error": node.error,
                },
                context.run_id,
            )
            return

        node.attempt += 1
        node.status = NodeStatus.RUNNING
        self._emit(
            GraphNodeStart,
            {"node_id": node.id, "kind": node.kind, "attempt": node.attempt},
            context.run_id,
        )
        try:
            outcome = await runner.run(node, context=context)
        except Exception as exc:  # noqa: BLE001 - surface runner failures into policy
            outcome = NodeOutcome(status=NodeStatus.FAILED, error=str(exc))

        self._apply_outcome(node, outcome)
        if node.status == NodeStatus.SUCCEEDED:
            self._emit(
                GraphNodeEnd,
                {
                    "node_id": node.id,
                    "kind": node.kind,
                    "status": node.status.value,
                    "attempt": node.attempt,
                },
                context.run_id,
            )
            return

        if node.status != NodeStatus.FAILED:
            node.status = NodeStatus.FAILED
            node.error = node.error or "runner_non_success"

        action = self.failure_policy.decide(node, error=node.error)
        if action == GraphFailureAction.RETRY and node.attempt < node.max_attempts:
            node.status = NodeStatus.PENDING
            self._emit(
                GraphNodeEnd,
                {
                    "node_id": node.id,
                    "kind": node.kind,
                    "status": "retry",
                    "attempt": node.attempt,
                    "error": node.error,
                },
                context.run_id,
            )
            return

        if action == GraphFailureAction.FAIL:
            # Clamp budget so ready_nodes will not re-queue this failure.
            node.max_attempts = node.attempt
            node.status = NodeStatus.FAILED
            self._emit(
                GraphNodeEnd,
                {
                    "node_id": node.id,
                    "kind": node.kind,
                    "status": node.status.value,
                    "attempt": node.attempt,
                    "error": node.error,
                },
                context.run_id,
            )
            return

        if action == GraphFailureAction.ESCALATE:
            if not self._allows(
                [GraphEscalate],
                tool_name="graph_escalate",
                run_id=context.run_id,
            ):
                node.status = NodeStatus.FAILED
                node.error = "escalation_denied"
            else:
                escalated = await self.escalation.handle(node, context=context)
                self._apply_outcome(node, escalated)
                if node.status == NodeStatus.SUCCEEDED:
                    self._emit(
                        GraphNodeEnd,
                        {
                            "node_id": node.id,
                            "kind": node.kind,
                            "status": "escalated_ok",
                            "attempt": node.attempt,
                        },
                        context.run_id,
                    )
                    return
                if (
                    node.status != NodeStatus.FAILED
                    and node.attempt < node.max_attempts
                ):
                    node.status = NodeStatus.PENDING
                    self._emit(
                        GraphNodeEnd,
                        {
                            "node_id": node.id,
                            "kind": node.kind,
                            "status": "escalated_retry",
                            "attempt": node.attempt,
                        },
                        context.run_id,
                    )
                    return
                node.status = NodeStatus.FAILED

        self._emit(
            GraphNodeEnd,
            {
                "node_id": node.id,
                "kind": node.kind,
                "status": node.status.value,
                "attempt": node.attempt,
                "error": node.error,
            },
            context.run_id,
        )


def registry_from_mapping(
    handlers: Mapping[str, NodeHandler],
    *,
    grants: Mapping[str, Sequence[object]] | None = None,
) -> GraphNodeRunnerRegistry:
    """Build a registry from kind → callable (convenience for hosts/tests)."""
    grant_map = grants or {}
    runners = [
        CallableGraphNodeRunner([kind], handler, grants=grant_map.get(kind))
        for kind, handler in handlers.items()
    ]
    return GraphNodeRunnerRegistry(runners)
