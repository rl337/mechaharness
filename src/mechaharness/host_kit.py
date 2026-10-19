"""Host-facing helpers for readable GraphExecutor / effectful wiring.

Orchestrator hosts (June and peers) often need two things that are easy to
get wrong when assembled by hand:

1. A :class:`~mechaharness.graph_executor.GraphExecutor` wired through
   :class:`~mechaharness.di.MechaHarnessConfig` (grants, runners, checkpoint
   store, crash probe) — without copying ten-line constructor assembly.
2. An effectful runner for the common non-idempotent pattern: **submit once**,
   **complete when the backend accepts a handle**, and **never silent-redispatch**
   an ``UNCERTAIN`` effect that has no handle.

This module is ergonomics on top of durable resume (DR-03..11). It does **not**
replace :class:`~mechaharness.graph_executor.EffectfulGraphNodeRunner` or own
long-running job observation — hosts keep post-accept control loops.

Quick start (doctest / pytest ``--doctest-modules``)::

    >>> import asyncio, tempfile
    >>> from pathlib import Path
    >>> from mechaharness.budget import BudgetPolicy
    >>> from mechaharness.external_effect import EffectDispatchResult
    >>> from mechaharness.graph import ExecutionGraph, GraphNode
    >>> from mechaharness.host_kit import (
    ...     SubmitOnceEffectfulRunner,
    ...     effectful_external_handle,
    ...     host_graph_executor,
    ... )
    >>> calls = {"n": 0}
    >>> async def submit(node, effect, context):
    ...     del effect, context
    ...     calls["n"] += 1
    ...     return EffectDispatchResult(
    ...         external_handle=f"job-{node.payload.get('task_id')}",
    ...     )
    >>> runner = SubmitOnceEffectfulRunner(
    ...     kinds=["coding_job"],
    ...     backend_id="host.coding",
    ...     submit=submit,
    ... )
    >>> path = Path(tempfile.mkdtemp()) / "runs.sqlite"
    >>> executor = host_graph_executor(
    ...     runners=[runner],
    ...     checkpoint_path=path,
    ...     agent_id="demo-host",
    ... )
    >>> graph = ExecutionGraph(id="g1", goal="dispatch once")
    >>> _ = graph.add_node(
    ...     GraphNode(
    ...         id="coding_job",
    ...         kind="coding_job",
    ...         payload={"task_id": "t1"},
    ...     )
    ... )
    >>> result = asyncio.run(
    ...     executor.run(
    ...         graph,
    ...         budget_policy=BudgetPolicy.unlimited(),
    ...         run_id="run-1",
    ...         skip_linkage=True,
    ...     )
    ... )
    >>> result.status, calls["n"], effectful_external_handle(result, "coding_job")
    ('ok', 1, 'job-t1')
    >>> executor.store.durability
    'durable'

Ephemeral (no checkpoint path) still injects a working executor::

    >>> executor_e = host_graph_executor(runners=[runner])
    >>> graph_e = ExecutionGraph(goal="ephemeral")
    >>> _ = graph_e.add_node(GraphNode(id="coding_job", kind="coding_job"))
    >>> result_e = asyncio.run(
    ...     executor_e.run(
    ...         graph_e,
    ...         budget_policy=BudgetPolicy.unlimited(),
    ...         run_id="run-e",
    ...         skip_linkage=True,
    ...     )
    ... )
    >>> result_e.status, executor_e.store.durability
    ('ok', 'ephemeral')

See also: ``docs/guides/dependency-injection.md`` (Host kit section) and
user story ``fangore_host_kit_submit_once``.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Union, cast

from pyiv.injector import Injector
from pyiv.time import DateTimeService

from mechaharness.authority_gate import AuthorityGate
from mechaharness.checkpoint_store import CheckpointStore
from mechaharness.consequence import ConsequencePolicy
from mechaharness.core.access import AccessControl, GraphEscalate, GraphExecute
from mechaharness.core.events import EventLog, InMemoryEventLog
from mechaharness.denial_store import DenialStore
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.external_effect import (
    CrashProbe,
    EffectDispatchResult,
    EffectReconciliation,
    EffectReconciliationAction,
    EffectRecord,
    EffectState,
    NoopCrashProbe,
)
from mechaharness.graph import GraphNode
from mechaharness.graph_executor import (
    EffectfulGraphNodeRunner,
    GraphExecutor,
    GraphNodeRunner,
    GraphNodeRunnerRegistry,
    GraphResult,
    GraphRunContext,
)
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore


class TappingEventLog:
    """Forward EventLog emits to an optional host callback (HF-05)."""

    def __init__(
        self,
        store: EventLog,
        *,
        on_event: Callable[[Any], None] | None = None,
    ) -> None:
        self._store = store
        self._on_event = on_event

    def emit(self, event: Any) -> None:
        self._store.emit(event)
        if self._on_event is not None:
            self._on_event(event)

    def query(self, **kwargs: Any) -> list[Any]:
        return self._store.query(**kwargs)

    def agents(self, **kwargs: Any) -> list[Any]:
        return self._store.agents(**kwargs)


def tapping_event_log(
    store: EventLog | None = None,
    *,
    on_event: Callable[[Any], None] | None = None,
) -> TappingEventLog:
    """Build a tapping EventLog for ``host_graph_executor(event_log=...)``.

    When ``store`` is omitted, uses a fresh ``InMemoryEventLog`` (explicit
    host-kit convenience, not a Config locator default).
    """
    return TappingEventLog(
        store if store is not None else InMemoryEventLog(),
        on_event=on_event,
    )

SubmitCallable = Callable[
    [GraphNode, EffectRecord, GraphRunContext],
    Union[EffectDispatchResult, Awaitable[EffectDispatchResult]],
]


class SubmitOnceEffectfulRunner(EffectfulGraphNodeRunner):
    """Effectful runner for non-idempotent submit that completes on accept.

    Hosts supply :meth:`kinds`, :meth:`backend_id`, and a ``submit`` callable
    (or override :meth:`dispatch`). This encodes the tiny intent:

    * dispatch once when the effect is ``INTENDED`` / first seen;
    * complete when the backend has accepted a handle (``observe`` / reconcile
      of ``ACCEPTED`` or ``UNCERTAIN`` **with** a handle);
    * escalate ``UNCERTAIN`` **without** a handle to ``NEEDS_ATTENTION`` —
      never silent-redispatch.

    Long-running job completion remains a host control-loop concern; this
    runner finishes the graph node at **accept**, not at remote job end.

    Reconciliation decisions (sync-friendly via ``asyncio.run``)::

        >>> import asyncio
        >>> from mechaharness.budget import Budget, BudgetPolicy
        >>> from mechaharness.external_effect import EffectRecord, EffectState
        >>> from mechaharness.graph import ExecutionGraph, GraphNode
        >>> from mechaharness.graph_executor import GraphRunContext
        >>> from mechaharness.host_kit import SubmitOnceEffectfulRunner
        >>> runner = SubmitOnceEffectfulRunner(
        ...     kinds=["coding_job"], backend_id="host.coding",
        ... )
        >>> graph = ExecutionGraph(goal="reconcile")
        >>> node = GraphNode(id="coding_job", kind="coding_job")
        >>> ctx = GraphRunContext(
        ...     graph=graph,
        ...     run_id="r1",
        ...     agent_id="host",
        ...     budget=Budget(BudgetPolicy.unlimited()),
        ... )
        >>> intended = EffectRecord(
        ...     effect_id="r1:coding_job:1",
        ...     run_id="r1",
        ...     node_id="coding_job",
        ...     state=EffectState.INTENDED,
        ... )
        >>> asyncio.run(runner.reconcile(node, effect=intended, context=ctx)).action.value
        'dispatch'
        >>> uncertain_ok = intended.model_copy(
        ...     update={
        ...         "state": EffectState.UNCERTAIN,
        ...         "external_handle": "job-9",
        ...     }
        ... )
        >>> rec = asyncio.run(
        ...     runner.reconcile(node, effect=uncertain_ok, context=ctx)
        ... )
        >>> rec.action.value, rec.external_handle
        ('complete', 'job-9')
        >>> uncertain_bad = intended.model_copy(
        ...     update={"state": EffectState.UNCERTAIN, "external_handle": None}
        ... )
        >>> bad = asyncio.run(
        ...     runner.reconcile(node, effect=uncertain_bad, context=ctx)
        ... )
        >>> bad.action.value, bad.error
        ('needs_attention', 'uncertain_without_handle')
    """

    def __init__(
        self,
        *,
        kinds: Sequence[str],
        backend_id: str,
        submit: SubmitCallable | None = None,
    ) -> None:
        if not kinds:
            raise ValueError("SubmitOnceEffectfulRunner requires at least one kind")
        self._kinds = list(kinds)
        self._backend_id = backend_id
        self._submit = submit

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def backend_id(self) -> str:
        return self._backend_id

    async def reconcile(
        self,
        node: GraphNode,
        *,
        effect: EffectRecord,
        context: GraphRunContext,
    ) -> EffectReconciliation:
        del node, context
        if effect.state is EffectState.INTENDED:
            return EffectReconciliation(action=EffectReconciliationAction.DISPATCH)
        if effect.state is EffectState.UNCERTAIN:
            if effect.external_handle:
                return EffectReconciliation(
                    action=EffectReconciliationAction.COMPLETE,
                    external_handle=effect.external_handle,
                    outcome_payload={
                        "external_run_id": effect.external_handle,
                        "external_handle": effect.external_handle,
                        "dispatch_phase": "reconciled_uncertain_accepted",
                    },
                )
            return EffectReconciliation(
                action=EffectReconciliationAction.NEEDS_ATTENTION,
                error="uncertain_without_handle",
            )
        if effect.state is EffectState.ACCEPTED and effect.external_handle:
            return EffectReconciliation(
                action=EffectReconciliationAction.COMPLETE,
                external_handle=effect.external_handle,
                outcome_payload={
                    "external_run_id": effect.external_handle,
                    "external_handle": effect.external_handle,
                    "dispatch_phase": "accepted",
                },
            )
        return EffectReconciliation(
            action=EffectReconciliationAction.NEEDS_ATTENTION,
            error=f"unexpected_effect_state:{effect.state}",
        )

    async def dispatch(
        self,
        node: GraphNode,
        *,
        effect: EffectRecord,
        context: GraphRunContext,
    ) -> EffectDispatchResult:
        if self._submit is None:
            raise TypeError(
                "SubmitOnceEffectfulRunner.dispatch requires a submit= callable "
                "or an override of dispatch()"
            )
        result = self._submit(node, effect, context)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, EffectDispatchResult):
            raise TypeError(
                f"submit callable must return EffectDispatchResult, got {type(result)!r}"
            )
        return result

    async def observe(
        self,
        node: GraphNode,
        *,
        effect: EffectRecord,
        context: GraphRunContext,
    ) -> EffectReconciliation:
        """Complete once the backend accepts the run — not when the job finishes."""
        del context
        handle = effect.external_handle
        if not handle:
            return EffectReconciliation(
                action=EffectReconciliationAction.NEEDS_ATTENTION,
                error="missing_external_handle",
            )
        return EffectReconciliation(
            action=EffectReconciliationAction.COMPLETE,
            external_handle=handle,
            outcome_payload={
                "external_run_id": handle,
                "external_handle": handle,
                "dispatch_phase": "accepted",
                "task_id": node.payload.get("task_id"),
                "backend_id": self.backend_id(),
            },
            outcome_evidence={"effect_id": effect.effect_id},
        )


def effectful_external_handle(result: GraphResult, node_id: str) -> str | None:
    """Return the external handle recorded on ``node_id`` after an effectful run.

    Prefers ``external_run_id``, then ``external_handle``, from the node's
    outcome payload. Returns ``None`` when the node is missing or has no
    handle::

        >>> from mechaharness.graph import ExecutionGraph, GraphNode
        >>> from mechaharness.graph_executor import GraphResult
        >>> from mechaharness.host_kit import effectful_external_handle
        >>> g = ExecutionGraph(goal="x")
        >>> n = GraphNode(id="job", kind="coding_job")
        >>> n.payload = {"external_run_id": "job-42"}
        >>> _ = g.add_node(n)
        >>> effectful_external_handle(
        ...     GraphResult(status="ok", graph=g, run_id="r"), "job"
        ... )
        'job-42'
        >>> effectful_external_handle(
        ...     GraphResult(status="ok", graph=g, run_id="r"), "missing"
        ... )
    """
    node = result.graph.nodes.get(node_id)
    if node is None:
        return None
    payload = dict(node.payload or {})
    handle = payload.get("external_run_id") or payload.get("external_handle")
    return str(handle) if handle else None


def host_graph_executor(
    *,
    runners: Sequence[GraphNodeRunner] | GraphNodeRunnerRegistry,
    checkpoint_store: CheckpointStore | None = None,
    checkpoint_path: str | Path | None = None,
    grants: Sequence[object] | None = None,
    crash_probe: CrashProbe | None = None,
    agent_id: str = "host",
    event_log: EventLog | None = None,
) -> GraphExecutor:
    """Build a :class:`GraphExecutor` via Config inject (blessed host path).

    Prefer this over hand-wiring EventLog / AccessControl / LinkageResolver /
    CheckpointStore / CrashProbe. Pass ``checkpoint_path`` for SQLite durability
    or ``checkpoint_store`` for a custom backend; omit both for the default
    ephemeral EventLog adapter.

    Pass ``event_log=`` (or :func:`tapping_event_log`) so hosts receive
    ``graph_node_start`` / ``graph_node_end`` without a dual executor path
    (HF-05).

    Defaults grant ``GraphExecute`` and ``GraphEscalate``. Override with
    ``grants=`` when the host needs a tighter pack. ``crash_probe`` is for
    acceptance / crash-window tests (see
    :class:`~mechaharness.external_effect.ArmedCrashProbe`).

    Mutually exclusive checkpoint knobs::

        >>> import tempfile
        >>> from pathlib import Path
        >>> from pyiv.time import PythonDateTimeService
        >>> from mechaharness.host_kit import (
        ...     SubmitOnceEffectfulRunner, host_graph_executor,
        ... )
        >>> from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore
        >>> runner = SubmitOnceEffectfulRunner(
        ...     kinds=["coding_job"], backend_id="host.coding",
        ... )
        >>> store = SqliteCheckpointStore(
        ...     Path(tempfile.mkdtemp()) / "x.sqlite",
        ...     datetime_service=PythonDateTimeService(),
        ... )
        >>> try:
        ...     host_graph_executor(
        ...         runners=[runner],
        ...         checkpoint_path="a.sqlite",
        ...         checkpoint_store=store,
        ...     )
        ... except ValueError as exc:
        ...     str(exc)
        'pass checkpoint_store or checkpoint_path, not both'
    """
    if checkpoint_store is not None and checkpoint_path is not None:
        raise ValueError("pass checkpoint_store or checkpoint_path, not both")

    if isinstance(runners, GraphNodeRunnerRegistry):
        registry = runners
    else:
        registry = GraphNodeRunnerRegistry(list(runners))

    grant_list = list(grants) if grants is not None else [GraphExecute, GraphEscalate]
    prebuilt_store = checkpoint_store
    sqlite_path = checkpoint_path
    probe = crash_probe
    aid = agent_id
    elog = event_log

    class _HostKitConfig(MechaHarnessConfig):
        def get_inference_class(self) -> type:
            return MockInferenceStrategy

        def get_harness_class(self) -> type:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return list(grant_list)

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

        def get_checkpoint_store(self) -> CheckpointStore | None:
            return prebuilt_store

        def get_crash_probe(self) -> CrashProbe | type[CrashProbe]:
            return probe if probe is not None else NoopCrashProbe

        def get_event_log(self) -> EventLog | None:
            return elog

        def configure(self) -> None:
            super().configure()
            if prebuilt_store is None and sqlite_path is not None:

                def make_sqlite(injector: Injector) -> CheckpointStore:
                    return SqliteCheckpointStore(
                        str(sqlite_path),
                        datetime_service=injector.inject(DateTimeService),
                    )

                self.register(CheckpointStore, make_sqlite, singleton=True)

    executor = cast(GraphExecutor, get_injector(_HostKitConfig).inject(GraphExecutor))
    executor.agent_id = aid
    return executor


def host_denial_store(*, denial_store: DenialStore | None = None) -> DenialStore:
    """Resolve the :class:`DenialStore` a host Config would bind (blessed host path).

    Default is the process-local ``InMemoryDenialStore`` (not restart-durable).
    Pass ``denial_store`` to bind a durable implementation; it is returned via the
    same Config inject so the gate from :func:`host_authority_gate` shares it.

        >>> from mechaharness.denial_store import equivalent_action_digest
        >>> store = host_denial_store()
        >>> digest = equivalent_action_digest("email.send", "bob@example.com")
        >>> _ = store.record(digest, reason="user_denied")
        >>> store.lookup(digest).reason
        'user_denied'
    """
    bound = denial_store

    class _HostDenialConfig(MechaHarnessConfig):
        def get_inference_class(self) -> type:
            return MockInferenceStrategy

        def get_harness_class(self) -> type:
            return PassThroughHarness

        def get_denial_store(self) -> DenialStore:
            if bound is not None:
                return bound
            return super().get_denial_store()

    return cast(DenialStore, get_injector(_HostDenialConfig).inject(DenialStore))


def host_authority_gate(
    *,
    grants: Sequence[object] | None = None,
    consequence: ConsequencePolicy | None = None,
    denial_store: DenialStore | None = None,
) -> AuthorityGate:
    """Build an :class:`AuthorityGate` via Config inject (blessed host path).

    ``grants`` feed deny-by-default access control (default: none, so any action
    that requires a grant is denied). ``consequence`` opts into approval for
    high-consequence actions; ``denial_store`` lets the gate remember denials.

        >>> from mechaharness.consequence import ActionConsequence, ConsequencePolicy
        >>> from mechaharness.core.access import GraphExecute
        >>> gate = host_authority_gate(
        ...     grants=[GraphExecute],
        ...     consequence=ConsequencePolicy(actions=[
        ...         ActionConsequence(action="email.send", consequence="high"),
        ...     ]),
        ... )
        >>> gate.evaluate(action="email.send", required_grants=[GraphExecute]).outcome
        'ask_human'
        >>> gate.evaluate(action="read", required_grants=[]).outcome
        'allow'
    """
    grant_list = list(grants) if grants is not None else []
    policy = consequence
    bound = denial_store

    class _HostGateConfig(MechaHarnessConfig):
        def get_inference_class(self) -> type:
            return MockInferenceStrategy

        def get_harness_class(self) -> type:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return list(grant_list)

        def get_denial_store(self) -> DenialStore:
            if bound is not None:
                return bound
            return super().get_denial_store()

        def configure(self) -> None:
            super().configure()

            def make_gate(injector: Injector) -> AuthorityGate:
                return AuthorityGate(
                    access=injector.inject(AccessControl),
                    denials=injector.inject(DenialStore),
                    consequence=policy,
                )

            self.register(AuthorityGate, make_gate, singleton=True)

    return cast(AuthorityGate, get_injector(_HostGateConfig).inject(AuthorityGate))
