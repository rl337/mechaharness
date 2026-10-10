"""Host-facing helpers for readable GraphExecutor / effectful wiring.

These helpers sit on top of :class:`~mechaharness.di.MechaHarnessConfig` so
orchestrators (e.g. June) can avoid hand-assembling
:class:`~mechaharness.graph_executor.GraphExecutor` collaborators or
re-implementing the common “submit once; complete on accept” effect machine.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Union

from mechaharness.checkpoint_store import CheckpointStore
from mechaharness.core.access import GraphEscalate, GraphExecute
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.external_effect import (
    CrashProbe,
    EffectDispatchResult,
    EffectRecord,
    EffectReconciliation,
    EffectReconciliationAction,
    EffectState,
    NoopCrashProbe,
)
from mechaharness.graph_executor import (
    EffectfulGraphNodeRunner,
    GraphExecutor,
    GraphNodeRunner,
    GraphNodeRunnerRegistry,
    GraphResult,
    GraphRunContext,
)
from mechaharness.graph import GraphNode
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore

SubmitCallable = Callable[
    [GraphNode, EffectRecord, GraphRunContext],
    Union[EffectDispatchResult, Awaitable[EffectDispatchResult]],
]


class SubmitOnceEffectfulRunner(EffectfulGraphNodeRunner):
    """Effectful runner for non-idempotent submit that completes on accept.

    Hosts supply :meth:`kinds`, :meth:`backend_id`, and a ``submit`` callable
    (or override :meth:`dispatch`). Reconciliation never silent-redispatches
    an ``UNCERTAIN`` effect without a handle — it completes with the handle or
    escalates to ``NEEDS_ATTENTION``.
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
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[misc]
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
    """Return the external handle recorded on ``node_id`` after an effectful run."""
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
) -> GraphExecutor:
    """Build a :class:`GraphExecutor` via Config inject (blessed host path).

    Prefer this over hand-wiring EventLog / AccessControl / LinkageResolver /
    CheckpointStore / CrashProbe. Pass ``checkpoint_path`` for SQLite durability
    or ``checkpoint_store`` for a custom backend; omit both for the default
    ephemeral EventLog adapter.
    """
    if checkpoint_store is not None and checkpoint_path is not None:
        raise ValueError("pass checkpoint_store or checkpoint_path, not both")

    if isinstance(runners, GraphNodeRunnerRegistry):
        registry = runners
    else:
        registry = GraphNodeRunnerRegistry(list(runners))

    grant_list = list(grants) if grants is not None else [GraphExecute, GraphEscalate]
    store = checkpoint_store
    if store is None and checkpoint_path is not None:
        store = SqliteCheckpointStore(str(checkpoint_path))
    probe = crash_probe if crash_probe is not None else NoopCrashProbe()
    aid = agent_id

    class _HostKitConfig(MechaHarnessConfig):
        def get_inference_class(self) -> type:
            return MockInferenceStrategy

        def get_harness_class(self) -> type:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return list(grant_list)

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

        def get_checkpoint_store(self) -> CheckpointStore:
            if store is not None:
                return store
            return super().get_checkpoint_store()

        def get_crash_probe(self) -> CrashProbe:
            return probe

    executor = get_injector(_HostKitConfig).inject(GraphExecutor)
    executor.agent_id = aid
    return executor
