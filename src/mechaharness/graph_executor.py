"""Injectable execution-graph runner (schedule, authorize, retry, escalate).

Hosts define node behavior as :class:`GraphNodeRunner` injectables and bind a
:class:`GraphNodeRunnerRegistry` via Config. The executor walks
:class:`~mechaharness.graph.ExecutionGraph` ready nodes, enforces grants,
emits lifecycle events, checkpoints through
:class:`~mechaharness.checkpoint_store.CheckpointStore`, and applies a
:class:`GraphFailurePolicy` / :class:`GraphEscalation` on failure.

Effectful runners opt into :class:`EffectfulGraphNodeRunner` so external
side effects get durable intent/acceptance and resume reconciliation
(DR-03..11). A host coding-job adapter + SQLite store looks like::

    >>> import asyncio, tempfile
    >>> from pathlib import Path
    >>> from mechaharness.budget import BudgetPolicy
    >>> from mechaharness.checkpoint_store import CheckpointStore
    >>> from mechaharness.core.access import GraphExecute
    >>> from mechaharness.di import MechaHarnessConfig, get_injector
    >>> from mechaharness.external_effect import (
    ...     EffectDispatchResult, EffectRecord, EffectReconciliation,
    ...     EffectReconciliationAction, EffectState,
    ... )
    >>> from mechaharness.graph import ExecutionGraph, GraphNode
    >>> from mechaharness.graph_executor import (
    ...     EffectfulGraphNodeRunner, GraphExecutor, GraphNodeRunnerRegistry,
    ...     GraphRunContext,
    ... )
    >>> from mechaharness.harness.pass_through import PassThroughHarness
    >>> from mechaharness.inference.mock import MockInferenceStrategy
    >>> from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore
    >>> class CodingJob(EffectfulGraphNodeRunner):
    ...     def __init__(self):
    ...         self.dispatches = 0
    ...     def kinds(self):
    ...         return ["coding_job"]
    ...     def backend_id(self):
    ...         return "host.coding_job"
    ...     async def reconcile(self, node, *, effect, context):
    ...         if effect.state is EffectState.INTENDED:
    ...             return EffectReconciliation(
    ...                 action=EffectReconciliationAction.DISPATCH,
    ...             )
    ...         return EffectReconciliation(
    ...             action=EffectReconciliationAction.COMPLETE,
    ...             external_handle=effect.external_handle or "job-1",
    ...             outcome_payload={"diff": "ok"},
    ...         )
    ...     async def dispatch(self, node, *, effect, context):
    ...         self.dispatches += 1
    ...         return EffectDispatchResult(external_handle="job-1")
    ...     async def observe(self, node, *, effect, context):
    ...         return EffectReconciliation(
    ...             action=EffectReconciliationAction.COMPLETE,
    ...             external_handle=effect.external_handle or "job-1",
    ...             outcome_payload={"diff": "ok"},
    ...         )
    >>> path = Path(tempfile.mkdtemp()) / "ckpt.sqlite"
    >>> runner = CodingJob()
    >>> class Cfg(MechaHarnessConfig):
    ...     def get_inference_class(self):
    ...         return MockInferenceStrategy
    ...     def get_harness_class(self):
    ...         return PassThroughHarness
    ...     def get_grants(self):
    ...         return [GraphExecute]
    ...     def get_node_runner_registry(self):
    ...         return GraphNodeRunnerRegistry([runner])
    ...     def get_checkpoint_store(self):
    ...         return SqliteCheckpointStore(path)
    >>> executor = get_injector(Cfg()).inject(GraphExecutor)
    >>> graph = ExecutionGraph(goal="ship feature")
    >>> _ = graph.add_node(GraphNode(id="job", kind="coding_job"))
    >>> result = asyncio.run(executor.run(
    ...     graph, budget_policy=BudgetPolicy.unlimited(), run_id="demo",
    ...     skip_linkage=True,
    ... ))
    >>> result.status, runner.dispatches
    ('ok', 1)
    >>> executor.store.durability
    'durable'
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
from mechaharness.checkpoint_store import CheckpointStore
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
from mechaharness.external_effect import (
    CrashProbe,
    EffectDispatchResult,
    EffectReconciliation,
    EffectReconciliationAction,
    EffectRecord,
    EffectState,
    InjectedProcessCrash,
)
from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
    NodeStatus,
)
from mechaharness.lifecycle_extension import (
    AfterGraphNode,
    BeforeGraphNode,
    LifecycleExtensionContext,
    LifecycleExtensionRegistry,
    ObserveAfter,
    ObserveBefore,
    empty_lifecycle_extension_registry,
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
    diagnostics: dict[str, Any] = Field(default_factory=dict)


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


class EffectfulGraphNodeRunner(GraphNodeRunner):
    """Opt-in runner for non-idempotent external side effects (DR-11).

    :meth:`GraphExecutor` orchestrates durable intent → uncertain → dispatch →
    accept → reduce. Hosts implement reconcile/dispatch/observe; pure
    :meth:`run` is unused for this path.
    """

    @abstractmethod
    def backend_id(self) -> str:
        """Stable provider identity (generic; not a Cursor type)."""

    def effect_id_for(self, node: GraphNode, *, run_id: str) -> str:
        """Stable effect identity for this node attempt context."""
        return f"{run_id}:{node.id}:{node.attempt}"

    @abstractmethod
    async def reconcile(
        self,
        node: GraphNode,
        *,
        effect: EffectRecord,
        context: GraphRunContext,
    ) -> EffectReconciliation:
        """Decide what to do with an intended/uncertain/accepted effect on resume."""

    @abstractmethod
    async def dispatch(
        self,
        node: GraphNode,
        *,
        effect: EffectRecord,
        context: GraphRunContext,
    ) -> EffectDispatchResult:
        """Perform the non-idempotent external call (only when allowed)."""

    @abstractmethod
    async def observe(
        self,
        node: GraphNode,
        *,
        effect: EffectRecord,
        context: GraphRunContext,
    ) -> EffectReconciliation:
        """Poll/complete an accepted effect into a terminal reconciliation."""

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del node, context
        raise TypeError(
            "EffectfulGraphNodeRunner is orchestrated by GraphExecutor; do not call run()"
        )


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
    ``get_graph_escalation`` / ``get_linkage_resolver`` /
    ``get_checkpoint_store`` rather than hand-building the executor.
    """

    def __init__(
        self,
        event_log: EventLog,
        access: AccessControl,
        runners: GraphNodeRunnerRegistry,
        failure_policy: GraphFailurePolicy,
        escalation: GraphEscalation,
        linkage_resolver: LinkageResolver,
        checkpoint_store: CheckpointStore,
        crash_probe: CrashProbe,
        lifecycle_extensions: LifecycleExtensionRegistry | None = None,
        *,
        agent_id: str | None = None,
        parent_agent_id: str | None = None,
    ) -> None:
        self.event_log = event_log
        self.access = access
        self.runners = runners
        self.failure_policy = failure_policy
        self.escalation = escalation
        self.linkage_resolver = linkage_resolver
        self.store = checkpoint_store
        self.crash_probe = crash_probe
        self.lifecycle_extensions = (
            lifecycle_extensions
            if lifecycle_extensions is not None
            else empty_lifecycle_extension_registry()
        )
        self.agent_id = agent_id or str(uuid4())
        self.parent_agent_id = parent_agent_id
        # Not a constructor DI param: Mapping[...] | None is not pyiv-injectable
        # on Python 3.10+ (GenericAlias). Hosts assign after inject when needed.
        self.fingerprint_parts: dict[str, Any] = {}
        self._diagnostics: dict[str, Any] = {
            "reconciliation_invoked": False,
            "runner_reentered": False,
            "effect_dispatches": 0,
        }

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
            diagnostics=dict(self._diagnostics),
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
        self._diagnostics = {
            "reconciliation_invoked": False,
            "runner_reentered": False,
            "effect_dispatches": 0,
            "resumed": resume,
            "checkpoint_durability": self.store.durability,
        }
        if resume:
            restored = self.store.latest(run_id=rid)
            if restored is not None:
                graph = restored
            # Interrupted mid-node work is re-queued; effect reconciliation
            # prevents duplicate external dispatch (DR-06 / DR-07).
            for node in graph.nodes.values():
                if node.status is NodeStatus.RUNNING:
                    node.status = NodeStatus.READY

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
        except InjectedProcessCrash:
            raise
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
        self.crash_probe.maybe_crash(
            "after_final_commit",
            run_id=rid,
            revision=self.store.latest_revision(run_id=rid),
        )
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

        if isinstance(runner, EffectfulGraphNodeRunner):
            await self._run_effectful_node(graph, node, context, runner)
            return

        node.attempt += 1
        node.status = NodeStatus.RUNNING
        self._emit(
            GraphNodeStart,
            {"node_id": node.id, "kind": node.kind, "attempt": node.attempt},
            context.run_id,
        )
        observe_only = frozenset({ObserveBefore, ObserveAfter})
        envelope = context.envelope
        before_ctx = LifecycleExtensionContext(
            boundary=BeforeGraphNode.key(),
            run_id=context.run_id,
            agent_id=self.agent_id,
            parent_agent_id=self.parent_agent_id,
            node_id=node.id,
            node_kind=node.kind,
            payload=dict(node.payload),
            envelope_grants=list(envelope.grants) if envelope is not None else [],
        )
        self.lifecycle_extensions.dispatch(
            BeforeGraphNode,
            before_ctx,
            event_log=self.event_log,
            envelope=envelope,
            allow_modes=observe_only,
        )
        try:
            outcome = await runner.run(node, context=context)
        except InjectedProcessCrash:
            raise
        except Exception as exc:  # noqa: BLE001 - surface runner failures into policy
            outcome = NodeOutcome(status=NodeStatus.FAILED, error=str(exc))

        after_ctx = LifecycleExtensionContext(
            boundary=AfterGraphNode.key(),
            run_id=context.run_id,
            agent_id=self.agent_id,
            parent_agent_id=self.parent_agent_id,
            node_id=node.id,
            node_kind=node.kind,
            payload={"status": outcome.status.value, "error": outcome.error},
            envelope_grants=list(envelope.grants) if envelope is not None else [],
        )
        self.lifecycle_extensions.dispatch(
            AfterGraphNode,
            after_ctx,
            event_log=self.event_log,
            envelope=envelope,
            allow_modes=observe_only,
        )

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
                node.error = node.error or "escalation_failed"

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

    async def _run_effectful_node(
        self,
        graph: ExecutionGraph,
        node: GraphNode,
        context: GraphRunContext,
        runner: EffectfulGraphNodeRunner,
    ) -> None:
        """Durable intent → uncertain → dispatch → accept → reduce (DR-03..07)."""
        del graph
        # Re-entry on resume: node may already be RUNNING from a prior crash.
        if node.attempt > 0 and node.status in {NodeStatus.RUNNING, NodeStatus.READY}:
            self._diagnostics["runner_reentered"] = True
        else:
            node.attempt += 1
        node.status = NodeStatus.RUNNING
        self._emit(
            GraphNodeStart,
            {
                "node_id": node.id,
                "kind": node.kind,
                "attempt": node.attempt,
                "effectful": True,
            },
            context.run_id,
        )

        effect = self.store.get_node_effect(
            run_id=context.run_id,
            node_id=node.id,
            node_attempt=node.attempt,
        )
        if effect is None and node.attempt > 1:
            # Fall back to any effect for this node (attempt bumped before crash).
            effect = self.store.get_node_effect(
                run_id=context.run_id,
                node_id=node.id,
            )

        # Terminal effects: reduce into the node without redispatch.
        if effect is not None and effect.state is EffectState.COMPLETED:
            outcome = NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload=dict(effect.detail.get("outcome_payload") or {}),
                evidence=dict(effect.detail.get("outcome_evidence") or {}),
            )
            self._finish_effectful_node(node, outcome, context, effect)
            return
        if effect is not None and effect.state is EffectState.FAILED:
            outcome = NodeOutcome(
                status=NodeStatus.FAILED,
                error=str(effect.detail.get("error") or "effect_failed"),
                payload=dict(effect.detail.get("outcome_payload") or {}),
                evidence=dict(effect.detail.get("outcome_evidence") or {}),
            )
            self._finish_effectful_node(node, outcome, context, effect)
            return
        if effect is not None and effect.state is EffectState.NEEDS_ATTENTION:
            outcome = NodeOutcome(
                status=NodeStatus.FAILED,
                error=str(
                    effect.detail.get("error") or "effect_needs_attention"
                ),
                payload=dict(effect.detail.get("outcome_payload") or {}),
                evidence=dict(effect.detail.get("outcome_evidence") or {}),
            )
            self._finish_effectful_node(node, outcome, context, effect)
            return

        may_dispatch = effect is None or effect.state is EffectState.INTENDED
        if effect is not None and effect.state in {
            EffectState.UNCERTAIN,
            EffectState.ACCEPTED,
            EffectState.INTENDED,
        }:
            self._diagnostics["reconciliation_invoked"] = True
            reconciliation = await runner.reconcile(
                node, effect=effect, context=context
            )
            reconciled = await self._apply_reconciliation(
                node, context, runner, effect, reconciliation
            )
            if reconciled is not None:
                self._finish_effectful_node(node, reconciled, context, effect)
                return
            may_dispatch = reconciliation.action is EffectReconciliationAction.DISPATCH
            effect = self.store.get_effect(effect.effect_id) or effect

        if not may_dispatch:
            # Uncertain without a clear dispatch/observe path → escalate attention.
            if effect is not None:
                effect = self.store.save_effect(
                    effect.model_copy(
                        update={
                            "state": EffectState.NEEDS_ATTENTION,
                            "recovery_boundary": "post_effect_pre_record",
                        }
                    )
                )
            outcome = NodeOutcome(
                status=NodeStatus.FAILED,
                error="effect_needs_attention",
            )
            self._finish_effectful_node(node, outcome, context, effect)
            return

        self.crash_probe.maybe_crash(
            "before_intent",
            run_id=context.run_id,
            node_id=node.id,
        )
        if effect is None:
            effect = EffectRecord(
                effect_id=runner.effect_id_for(node, run_id=context.run_id),
                run_id=context.run_id,
                node_id=node.id,
                node_attempt=node.attempt,
                backend_id=runner.backend_id(),
                state=EffectState.INTENDED,
                recovery_boundary="planning",
            )
            effect = self.store.save_effect(effect)
            node.recovery_boundary = "planning"
            self.store.save(
                context.graph,
                run_id=context.run_id,
                boundary="planning",
                fingerprint=context.config_fingerprint,
            )

        self.crash_probe.maybe_crash(
            "after_intent_before_call",
            run_id=context.run_id,
            node_id=node.id,
            effect_id=effect.effect_id,
        )

        # Mark uncertain before the external call so a crash mid-call reconciles.
        effect = self.store.save_effect(
            effect.model_copy(
                update={
                    "state": EffectState.UNCERTAIN,
                    "recovery_boundary": "dispatch",
                }
            )
        )
        node.recovery_boundary = "dispatch"
        self.store.save(
            context.graph,
            run_id=context.run_id,
            boundary="dispatch",
            fingerprint=context.config_fingerprint,
        )

        self._diagnostics["effect_dispatches"] = (
            int(self._diagnostics.get("effect_dispatches") or 0) + 1
        )
        dispatched = await runner.dispatch(node, effect=effect, context=context)

        self.crash_probe.maybe_crash(
            "after_accept_before_record",
            run_id=context.run_id,
            node_id=node.id,
            effect_id=effect.effect_id,
            external_handle=dispatched.external_handle,
        )

        effect = self.store.save_effect(
            effect.model_copy(
                update={
                    "state": EffectState.ACCEPTED,
                    "external_handle": dispatched.external_handle,
                    "recovery_boundary": "post_effect_pre_record",
                    "detail": {**effect.detail, **dispatched.detail},
                }
            )
        )
        node.recovery_boundary = "post_effect_pre_record"
        self.store.save(
            context.graph,
            run_id=context.run_id,
            boundary="post_effect_pre_record",
            fingerprint=context.config_fingerprint,
        )
        self.crash_probe.maybe_crash(
            "after_accept_recorded",
            run_id=context.run_id,
            node_id=node.id,
            effect_id=effect.effect_id,
            external_handle=effect.external_handle,
        )

        observed = await runner.observe(node, effect=effect, context=context)
        reduced = await self._apply_reconciliation(
            node, context, runner, effect, observed
        )
        if reduced is None:
            reduced = NodeOutcome(
                status=NodeStatus.FAILED,
                error="effect_observe_incomplete",
            )
        self._finish_effectful_node(node, reduced, context, effect)
        # Crash after node reduce, before the loop's next graph checkpoint (DR-10).
        self.crash_probe.maybe_crash(
            "after_reduce_before_checkpoint",
            run_id=context.run_id,
            node_id=node.id,
            effect_id=effect.effect_id,
        )

    async def _apply_reconciliation(
        self,
        node: GraphNode,
        context: GraphRunContext,
        runner: EffectfulGraphNodeRunner,
        effect: EffectRecord,
        reconciliation: EffectReconciliation,
    ) -> NodeOutcome | None:
        """Apply a host reconciliation decision; return outcome if terminal."""
        if reconciliation.action is EffectReconciliationAction.DISPATCH:
            return None
        if reconciliation.action is EffectReconciliationAction.OBSERVE:
            if reconciliation.external_handle and not effect.external_handle:
                effect = self.store.save_effect(
                    effect.model_copy(
                        update={
                            "state": EffectState.ACCEPTED,
                            "external_handle": reconciliation.external_handle,
                            "recovery_boundary": "post_effect_pre_record",
                        }
                    )
                )
            observed = await runner.observe(node, effect=effect, context=context)
            return await self._apply_reconciliation(
                node, context, runner, effect, observed
            )
        if reconciliation.action is EffectReconciliationAction.COMPLETE:
            detail = {
                **effect.detail,
                "outcome_payload": reconciliation.outcome_payload,
                "outcome_evidence": reconciliation.outcome_evidence,
            }
            self.store.save_effect(
                effect.model_copy(
                    update={
                        "state": EffectState.COMPLETED,
                        "external_handle": reconciliation.external_handle
                        or effect.external_handle,
                        "recovery_boundary": "reduce",
                        "detail": detail,
                    }
                )
            )
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload=dict(reconciliation.outcome_payload),
                evidence=dict(reconciliation.outcome_evidence),
            )
        if reconciliation.action is EffectReconciliationAction.FAIL:
            self.store.save_effect(
                effect.model_copy(
                    update={
                        "state": EffectState.FAILED,
                        "recovery_boundary": "reduce",
                        "detail": {
                            **effect.detail,
                            "error": reconciliation.error or "effect_failed",
                            "outcome_payload": reconciliation.outcome_payload,
                            "outcome_evidence": reconciliation.outcome_evidence,
                        },
                    }
                )
            )
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error=reconciliation.error or "effect_failed",
                payload=dict(reconciliation.outcome_payload),
                evidence=dict(reconciliation.outcome_evidence),
            )
        # needs_attention
        self.store.save_effect(
            effect.model_copy(
                update={
                    "state": EffectState.NEEDS_ATTENTION,
                    "recovery_boundary": "post_effect_pre_record",
                    "detail": {
                        **effect.detail,
                        **reconciliation.detail,
                        "error": reconciliation.error or "effect_needs_attention",
                    },
                }
            )
        )
        return NodeOutcome(
            status=NodeStatus.FAILED,
            error=reconciliation.error or "effect_needs_attention",
            payload=dict(reconciliation.outcome_payload),
            evidence=dict(reconciliation.outcome_evidence),
        )

    def _finish_effectful_node(
        self,
        node: GraphNode,
        outcome: NodeOutcome,
        context: GraphRunContext,
        effect: EffectRecord | None,
    ) -> None:
        self._apply_outcome(node, outcome)
        if effect is not None and outcome.status is NodeStatus.SUCCEEDED:
            node.recovery_boundary = "reduce"
        # Terminal effect outcomes must not be re-queued by ready_nodes.
        if outcome.status is NodeStatus.FAILED:
            node.max_attempts = node.attempt
        self._charge_node(node, outcome, context.budget)
        self._emit(
            GraphNodeEnd,
            {
                "node_id": node.id,
                "kind": node.kind,
                "status": node.status.value,
                "attempt": node.attempt,
                "error": node.error,
                "effect_id": effect.effect_id if effect else None,
                "effect_state": effect.state.value if effect else None,
                "budget_spent": context.budget.spent,
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
