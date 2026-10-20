"""Story acceptance probes for host DI / host-kit stories."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field
from pyiv.key import Matched, Named

from mechaharness.budget import BudgetPolicy
from mechaharness.core.access import AccessPolicy, GraphExecute, InMemoryAccessControl
from mechaharness.core.completer import Completer
from mechaharness.core.environment import NoOpInferenceEnvironment
from mechaharness.core.events import InMemoryEventLog
from mechaharness.di import MechaHarnessConfig, _expose_ctor_type_hints, get_injector
from mechaharness.external_effect import EffectDispatchResult, EffectRecord, EffectState
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphNodeRunnerRegistry,
    NodeOutcome,
)
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.host_kit import (
    SubmitOnceEffectfulRunner,
    effectful_external_handle,
    host_graph_executor,
)
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference_capture import EvaluationOnlyCapture
from mechaharness.linkage_resolver import DefaultLinkageResolver
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore


class CheckCompleterFlavorsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flavor_tags: list[str] = Field(default_factory=lambda: ["reason", "code", "deep"])
    matched_required: list[str] = Field(default_factory=lambda: ["reason", "code"])


class CheckInferenceCaptureCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_inference_capture: str = "training_grade"


class HostKitCaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    mode: str = "dispatch"
    durable: bool = True
    run_id: str | None = None
    task_id: str = "t1"
    node_id: str = "coding_job"
    seed: dict[str, Any] = Field(default_factory=dict)


class HostKitSubmitOnceCommand(HostKitCaseSpec):
    """One submit-once claim (split matrices across scenario YAML files)."""

    model_config = ConfigDict(extra="forbid")


def run_check_completer_flavors(body: CheckCompleterFlavorsCommand) -> dict[str, Any]:
    from mechaharness.inference.mock import MockInferenceStrategy

    flavor_tags = list(body.flavor_tags)
    matched_required = list(body.matched_required)

    class FlavorCompleter(MockInferenceStrategy):
        def __init__(self) -> None:
            super().__init__()
            self.flavor = "code"

    class CodeReviewHost:
        def __init__(self, inference: Completer, via_matched: Completer) -> None:
            self.inference = inference
            self.via_matched = via_matched

    # Real annotation objects (not postponed strings) so Named/Matched see tag lists.
    CodeReviewHost.__init__.__annotations__ = {
        "inference": Annotated[Completer, Named(flavor_tags)],
        "via_matched": Annotated[Completer, Matched(required=matched_required)],
        "return": None,
    }

    class StoryConfig(MechaHarnessConfig):
        def __init__(self) -> None:
            self._default = MockInferenceStrategy()
            super().__init__()

        def get_inference_class(self) -> type[InferenceStrategy]:
            return type(self._default)

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def completer_bindings(self) -> list[tuple[Named, type[Completer]]]:
            return [
                (Named(["reason"], default=True), self.get_inference_class()),
                (Named(flavor_tags), FlavorCompleter),
            ]

        def configure(self) -> None:
            super().configure()
            self.register_instance(InferenceStrategy, self._default)
            _expose_ctor_type_hints(CodeReviewHost)
            self.register(CodeReviewHost, CodeReviewHost)

    injector = get_injector(StoryConfig())
    default = injector.inject(Completer)
    strategy = injector.inject(InferenceStrategy)
    host = injector.inject(CodeReviewHost)
    return {
        "default_is_inference": default is strategy,
        "flavor_selected": getattr(host.inference, "flavor", None) == "code",
        "matched_selects_flavor": host.via_matched is host.inference,
    }


def run_check_inference_capture(
    body: CheckInferenceCaptureCommand,
) -> dict[str, Any]:
    reg = GraphNodeRunnerRegistry()

    async def ok(node: GraphNode, context: object) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    reg.register(CallableGraphNodeRunner(["compute"], ok))
    access = InMemoryAccessControl(
        InMemoryEventLog(), AccessPolicy(grants=[GraphExecute])
    )
    resolver = DefaultLinkageResolver(
        reg,
        access,
        NoOpInferenceEnvironment(),
        inference_capture=EvaluationOnlyCapture(),
    )
    graph = ExecutionGraph(goal="capture")
    graph.add_node(GraphNode(id="a", kind="compute"))
    report = resolver.resolve(
        graph,
        fingerprint_parts={
            "required_inference_capture": body.required_inference_capture
        },
    )
    return {
        "linkage_ok": report.ok,
        "codes_exactly": sorted(e.code for e in report.edges),
    }


class _SubmitLog:
    def __init__(self) -> None:
        self.count = 0
        self.handles: list[str] = []

    async def submit(
        self,
        node: GraphNode,
        effect: EffectRecord,
        context: object,
    ) -> EffectDispatchResult:
        del effect, context
        self.count += 1
        handle = f"job-{node.payload.get('task_id') or node.id}-{self.count}"
        self.handles.append(handle)
        return EffectDispatchResult(
            external_handle=handle,
            detail={"backend_id": "cli"},
        )


def _make_job_graph(*, node_id: str, task_id: str) -> ExecutionGraph:
    graph = ExecutionGraph(id="g1", goal="host-kit")
    graph.add_node(
        GraphNode(
            id=node_id,
            kind="coding_job",
            goal="submit",
            payload={"task_id": task_id},
        )
    )
    return graph


async def run_host_kit_submit_once(
    body: HostKitSubmitOnceCommand,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mh-cli-host-kit-") as tmp:
        log = _SubmitLog()
        runner = SubmitOnceEffectfulRunner(
            kinds=["coding_job"],
            backend_id="cli.coding",
            submit=log.submit,
        )
        run_id = body.run_id or f"cli-{body.id}"
        db = Path(tmp) / f"{body.id}.sqlite"
        if body.durable:
            executor = host_graph_executor(
                runners=[runner],
                checkpoint_path=db,
                agent_id="cli-host-kit",
            )
        else:
            executor = host_graph_executor(
                runners=[runner],
                agent_id="cli-host-kit",
            )
        store = executor.store
        node_id = body.node_id
        if body.mode == "dispatch":
            result = await executor.run(
                _make_job_graph(node_id=node_id, task_id=body.task_id),
                budget_policy=BudgetPolicy.unlimited(),
                run_id=run_id,
                skip_linkage=True,
            )
        elif body.mode == "resume_seeded":
            if not isinstance(store, SqliteCheckpointStore):
                raise ValueError(
                    "resume_seeded requires durable SqliteCheckpointStore"
                )
            effect_states = {s.value: s for s in EffectState}
            node_statuses = {s.value: s for s in NodeStatus}
            seed = body.seed
            effect_state = effect_states[
                str(seed.get("effect_state") or "uncertain")
            ]
            handle = seed.get("external_handle")
            attempt = int(seed.get("node_attempt") or 1)
            node_status = node_statuses[str(seed.get("node_status") or "running")]
            graph = _make_job_graph(node_id=node_id, task_id=body.task_id)
            graph.nodes[node_id].attempt = attempt
            graph.nodes[node_id].status = node_status
            store.save_effect(
                EffectRecord(
                    effect_id=f"{run_id}:{node_id}:{attempt}",
                    run_id=run_id,
                    node_id=node_id,
                    node_attempt=attempt,
                    backend_id="cli.coding",
                    state=effect_state,
                    external_handle=str(handle) if handle else None,
                    recovery_boundary="dispatch",
                )
            )
            store.save(graph, run_id=run_id, boundary="dispatch", fingerprint="fp")
            result = await executor.run(
                _make_job_graph(node_id=node_id, task_id=body.task_id),
                budget_policy=BudgetPolicy.unlimited(),
                run_id=run_id,
                resume=True,
                skip_linkage=True,
            )
        else:
            raise ValueError(f"unknown host_kit mode {body.mode!r}")
        out = {
            "status": result.status,
            "dispatch_count": log.count,
            "external_handle": effectful_external_handle(result, node_id),
            "durability": store.durability,
            "reconciliation_invoked": bool(
                result.diagnostics.get("reconciliation_invoked")
            ),
        }
        if hasattr(store, "close"):
            store.close()
        return out



__all__ = [
    "CheckCompleterFlavorsCommand",
    "CheckInferenceCaptureCommand",
    "HostKitSubmitOnceCommand",
    "run_check_completer_flavors",
    "run_check_inference_capture",
    "run_host_kit_submit_once",
]
