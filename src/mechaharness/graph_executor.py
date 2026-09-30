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

from mechaharness.budget import Budget, BudgetLevel, BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
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
from mechaharness.linkage_resolver import (
    LinkageError,
    LinkageResolver,
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
    cost_units: float | None = None


@dataclass(frozen=True)
class GraphRunContext:
    """Per-run identity passed to node runners and escalation."""

    graph: ExecutionGraph
    run_id: str
    agent_id: str
    budget: Budget
    parent_agent_id: str | None = None
    envelope: CapabilityEnvelope | None = None
    config_fingerprint: str | None = None


class GraphResult(BaseModel):
    """Outcome of :meth:`GraphExecutor.run`."""

    model_config = ConfigDict(extra="allow")

    status: Literal["ok", "failed", "denied", "stalled", "soft_exhausted"]
    graph: ExecutionGraph
    run_id: str
    events: list[Event] = Field(default_factory=list)
    error: str | None = None
    budget_spent: float = 0.0
    budget_level: str = BudgetLevel.OK.value


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
    ``get_graph_escalation`` / ``get_linkage_resolver`` rather than
    hand-building the executor.
    """

    def __init__(
        self,
        event_log: EventLog,
        access: AccessControl,
        runners: GraphNodeRunnerRegistry,
        failure_policy: GraphFailurePolicy,
        escalation: GraphEscalation,
        linkage_resolver: LinkageResolver,
        *,
        agent_id: str | None = None,
        parent_agent_id: str | None = None,
        fingerprint_parts: Mapping[str, Any] | None = None,
    ) -> None:
        self.event_log = event_log
        self.access = access
        self.runners = runners
        self.failure_policy = failure_policy
        self.escalation = escalation
        self.linkage_resolver = linkage_resolver
        self.agent_id = agent_id or str(uuid4())
        self.parent_agent_id = parent_agent_id
        self.fingerprint_parts = dict(fingerprint_parts or {})
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

    def _terminal_status(
        self, graph: ExecutionGraph
    ) -> Literal["ok", "failed", "stalled", "soft_exhausted"]:
        statuses = {n.status for n in graph.nodes.values()}
        if statuses and statuses <= {NodeStatus.SUCCEEDED}:
            return "ok"
        if statuses and statuses <= {NodeStatus.SUCCEEDED, NodeStatus.CANCELLED}:
            if NodeStatus.CANCELLED in statuses:
                return "soft_exhausted"
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

    def _cancel_open_nodes(self, graph: ExecutionGraph, *, reason: str) -> None:
        open_statuses = {
            NodeStatus.PENDING,
            NodeStatus.READY,
            NodeStatus.BLOCKED,
        }
        for node in graph.nodes.values():
            if node.status in open_statuses:
                node.status = NodeStatus.CANCELLED
                node.error = reason

    def _fail_open_nodes(self, graph: ExecutionGraph, *, reason: str) -> None:
        open_statuses = {
            NodeStatus.PENDING,
            NodeStatus.READY,
            NodeStatus.BLOCKED,
            NodeStatus.RUNNING,
        }
        for node in graph.nodes.values():
            if node.status in open_statuses:
                node.status = NodeStatus.FAILED
                node.error = reason

    def _charge_node(
        self,
        node: GraphNode,
        outcome: NodeOutcome | None,
        budget: Budget,
        *,
        subgraph: bool = False,
    ) -> BudgetLevel:
        """Charge cost for a finished node attempt into ``budget``."""
        if subgraph:
            # Nested run already charged the shared ledger.
            return budget.status()
        if outcome is not None and outcome.cost_units is not None:
            amount = float(outcome.cost_units)
        else:
            raw = node.payload.get("cost_units", 1.0)
            try:
                amount = float(raw)
            except (TypeError, ValueError):
                amount = 1.0
        return budget.charge(amount, node_id=node.id, kind=node.kind)

    def _result(
        self,
        *,
        status: Literal["ok", "failed", "denied", "stalled", "soft_exhausted"],
        graph: ExecutionGraph,
        run_id: str,
        budget: Budget,
        error: str | None = None,
    ) -> GraphResult:
        return GraphResult(
            status=status,
            graph=graph,
            run_id=run_id,
            events=self.event_log.query(run_id=run_id),
            error=error,
            budget_spent=budget.spent,
            budget_level=budget.status().value,
        )

    async def run(
        self,
        graph: ExecutionGraph,
        *,
        budget_policy: BudgetPolicy,
        budget: Budget | None = None,
        run_id: str | None = None,
        resume: bool = False,
        envelope: CapabilityEnvelope | None = None,
        skip_linkage: bool = False,
    ) -> GraphResult:
        """Execute ``graph`` until completion, denial, stall, or budget failure.

        ``budget_policy`` is required. Pass a shared ``budget`` for nested
        subgraphs so spend aggregates; otherwise a fresh :class:`Budget` is
        created from the policy.

        Soft limit: cancel remaining open work and return ``soft_exhausted``.
        Hard limit: fail open nodes and return ``failed`` with prejudice.
        ``BudgetPolicy.hard_limit=None`` means unlimited hard ceiling.
        """
        rid = run_id or graph.id
        ledger = budget if budget is not None else Budget(budget_policy)
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
            return self._result(
                status="denied",
                graph=graph,
                run_id=rid,
                budget=ledger,
                error="missing_grant:core:graph.execute",
            )

        report = None
        fingerprint = graph.config_fingerprint
        if not skip_linkage:
            report = self.linkage_resolver.resolve(
                graph,
                envelope=envelope,
                fingerprint_parts=self.fingerprint_parts,
            )
            fingerprint = report.fingerprint or fingerprint
            if resume:
                prior = self.store.latest_fingerprint(run_id=rid) or graph.config_fingerprint
                if prior and fingerprint and prior != fingerprint:
                    err = f"incompatible_checkpoint_fingerprint:{prior}!={fingerprint}"
                    self._emit(GraphStart, {"goal": graph.goal, "status": "failed"}, rid)
                    self._emit(GraphEnd, {"status": "failed", "error": err}, rid)
                    return self._result(
                        status="failed", graph=graph, run_id=rid, budget=ledger, error=err
                    )
            if not report.ok:
                err = f"linkage_failed:{';'.join(e.code for e in report.edges)}"
                self._emit(
                    GraphStart,
                    {
                        "goal": graph.goal,
                        "node_count": len(graph.nodes),
                        "status": "failed",
                        "linkage_edges": [e.model_dump() for e in report.edges],
                    },
                    rid,
                )
                self._emit(GraphEnd, {"status": "failed", "error": err}, rid)
                return self._result(
                    status="failed", graph=graph, run_id=rid, budget=ledger, error=err
                )

        if fingerprint:
            graph.config_fingerprint = fingerprint

        context = GraphRunContext(
            graph=graph,
            run_id=rid,
            agent_id=self.agent_id,
            budget=ledger,
            parent_agent_id=self.parent_agent_id,
            envelope=envelope,
            config_fingerprint=fingerprint,
        )
        self._emit(
            GraphStart,
            {
                "goal": graph.goal,
                "node_count": len(graph.nodes),
                "kinds": self.runners.kinds(),
                "config_fingerprint": fingerprint,
                "budget_soft": budget_policy.soft_limit,
                "budget_hard": budget_policy.hard_limit,
                "budget_spent": ledger.spent,
            },
            rid,
        )
        self.store.save(graph, run_id=rid, boundary="dispatch", fingerprint=fingerprint)

        try:
            await self._run_loop(graph, context)
        except GraphExecutorError as exc:
            self.store.save(graph, run_id=rid, boundary="commit", fingerprint=fingerprint)
            if str(exc) == "hard_budget_exceeded":
                self._fail_open_nodes(graph, reason="hard_budget_exceeded")
                self._emit(
                    GraphEnd,
                    {
                        "status": "failed",
                        "error": str(exc),
                        "budget_spent": ledger.spent,
                        "budget_level": ledger.status().value,
                    },
                    rid,
                )
                return self._result(
                    status="failed",
                    graph=graph,
                    run_id=rid,
                    budget=ledger,
                    error="hard_budget_exceeded",
                )
            status = self._terminal_status(graph)
            self._emit(GraphEnd, {"status": status, "error": str(exc)}, rid)
            return self._result(
                status=status if status != "ok" else "failed",
                graph=graph,
                run_id=rid,
                budget=ledger,
                error=str(exc),
            )
        except LinkageError as exc:
            self.store.save(graph, run_id=rid, boundary="commit", fingerprint=fingerprint)
            self._emit(GraphEnd, {"status": "failed", "error": str(exc)}, rid)
            return self._result(
                status="failed", graph=graph, run_id=rid, budget=ledger, error=str(exc)
            )

        self.store.save(graph, run_id=rid, boundary="commit", fingerprint=fingerprint)
        status = self._terminal_status(graph)
        end_payload: dict[str, Any] = {
            "status": status,
            "node_count": len(graph.nodes),
            "budget_spent": ledger.spent,
            "budget_level": ledger.status().value,
        }
        error = None
        if status == "soft_exhausted":
            error = "soft_budget_exceeded"
            end_payload["error"] = error
        elif status != "ok":
            error = "graph_incomplete"
            end_payload["error"] = error
        self._emit(GraphEnd, end_payload, rid)
        return self._result(
            status=status, graph=graph, run_id=rid, budget=ledger, error=error
        )

    async def _run_loop(self, graph: ExecutionGraph, context: GraphRunContext) -> None:
        # Bound iterations: each node may attempt up to max_attempts (+ escalation).
        loop_budget = (
            sum(max(1, n.max_attempts) for n in graph.nodes.values()) + len(graph.nodes) + 1
        )
        for _ in range(loop_budget):
            level = context.budget.status()
            if level is BudgetLevel.HARD:
                raise GraphExecutorError("hard_budget_exceeded")
            if level is BudgetLevel.SOFT:
                self._cancel_open_nodes(graph, reason="soft_budget_exceeded")
                return
            ready = graph.ready_nodes()
            if not ready:
                return
            conflicts = graph.concurrent_write_conflicts([n.id for n in ready])
            if conflicts and len(ready) > 1:
                # Sequential safety: pick one non-conflicting node; if all conflict, run first.
                ready = [ready[0]]
            node = ready[0]
            await self._run_node(graph, node, context)
            if context.budget.status() is BudgetLevel.HARD:
                raise GraphExecutorError("hard_budget_exceeded")
            self.store.save(graph, run_id=context.run_id, boundary="reduce")
        raise GraphExecutorError("exceeded graph execution budget")

    async def _run_subgraph_node(
        self,
        graph: ExecutionGraph,
        node: GraphNode,
        context: GraphRunContext,
    ) -> None:
        """Execute an embedded child graph as an observable nested graph run."""
        del graph
        node.attempt += 1
        node.status = NodeStatus.RUNNING
        self._emit(
            GraphNodeStart,
            {
                "node_id": node.id,
                "kind": node.kind,
                "attempt": node.attempt,
                "subgraph": True,
            },
            context.run_id,
        )
        raw = node.subgraph or node.payload.get("subgraph")
        if not isinstance(raw, dict):
            node.status = NodeStatus.FAILED
            node.error = "missing_subgraph"
            self._charge_node(node, None, context.budget, subgraph=True)
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
        child = ExecutionGraph.resume(raw)
        child_run_id = f"{context.run_id}:{node.id}"
        # Share the parent ledger so nested spend aggregates.
        child_result = await self.run(
            child,
            budget_policy=context.budget.policy,
            budget=context.budget,
            run_id=child_run_id,
            envelope=context.envelope,
        )
        node.payload = {
            **node.payload,
            "child_status": child_result.status,
            "child_run_id": child_run_id,
            "child_graph_id": child.id,
            "budget_spent": child_result.budget_spent,
        }
        if child_result.status == "ok":
            node.status = NodeStatus.SUCCEEDED
            node.error = None
        elif child_result.status == "soft_exhausted":
            # Parent soft wind-down already reflected on shared budget.
            node.status = NodeStatus.SUCCEEDED
            node.error = None
        else:
            node.status = NodeStatus.FAILED
            node.error = child_result.error or f"subgraph_{child_result.status}"
        self._emit(
            GraphNodeEnd,
            {
                "node_id": node.id,
                "kind": node.kind,
                "status": node.status.value,
                "attempt": node.attempt,
                "error": node.error,
                "child_run_id": child_run_id,
                "budget_spent": context.budget.spent,
            },
            context.run_id,
        )

    async def _run_node(
        self,
        graph: ExecutionGraph,
        node: GraphNode,
        context: GraphRunContext,
    ) -> None:
        if node.kind == "subgraph" or node.subgraph:
            await self._run_subgraph_node(graph, node, context)
            return
        runner = self.runners.get(node.kind)
        if runner is None:
            node.status = NodeStatus.FAILED
            node.error = f"no_runner:{node.kind}"
            node.attempt += 1
            self._charge_node(node, None, context.budget)
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
            self._charge_node(node, None, context.budget)
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
        self._charge_node(node, outcome, context.budget)
        if node.status == NodeStatus.SUCCEEDED:
            self._emit(
                GraphNodeEnd,
                {
                    "node_id": node.id,
                    "kind": node.kind,
                    "status": node.status.value,
                    "attempt": node.attempt,
                    "budget_spent": context.budget.spent,
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
            # Clamp attempt budget so ready_nodes will not re-queue this failure.
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
