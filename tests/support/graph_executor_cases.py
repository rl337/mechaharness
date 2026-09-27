"""Load and interpret declarative GraphExecutor case fixtures."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mechaharness.core.access import (
    FsRead,
    FsWrite,
    GraphEscalate,
    GraphExecute,
    MediaImage,
    grant_key,
)
from mechaharness.di import MechaHarnessConfig
from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    DefaultGraphFailurePolicy,
    GraphEscalation,
    GraphFailureAction,
    GraphFailurePolicy,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
    RejectGraphEscalation,
)
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.tools.base import ToolRegistry

CASES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "graph_executor"

_GRANT_ALIASES: dict[str, object] = {
    "core:graph.execute": GraphExecute,
    "core:graph.escalate": GraphEscalate,
    "core:fs.read": FsRead,
    "core:fs.write": FsWrite,
    "core:media.image": MediaImage,
}

_STATUS = {s.value: s for s in NodeStatus}


@dataclass
class CallLog:
    """Per-kind invocation counts and ordered node ids."""

    by_kind: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    order: list[str] = field(default_factory=list)

    def record(self, kind: str, node_id: str) -> None:
        self.by_kind[kind] += 1
        self.order.append(node_id)


@dataclass(frozen=True)
class GraphExecutorCase:
    """One fixture file under ``tests/fixtures/graph_executor/``."""

    path: Path
    data: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.data.get("id") or self.path.stem)


def iter_cases() -> list[GraphExecutorCase]:
    if not CASES_DIR.is_dir():
        return []
    cases: list[GraphExecutorCase] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"{path}: case root must be an object")
        cases.append(GraphExecutorCase(path=path, data=data))
    return cases


def resolve_grants(raw: Sequence[str] | None) -> list[object]:
    out: list[object] = []
    for item in raw or []:
        key = grant_key(item) if not isinstance(item, str) else item
        out.append(_GRANT_ALIASES.get(key, key))
    return out


def build_graph(spec: dict[str, Any]) -> ExecutionGraph:
    graph = ExecutionGraph(goal=str(spec.get("goal") or ""))
    for raw in spec.get("nodes") or []:
        status = raw.get("status")
        node = GraphNode(
            id=str(raw["id"]),
            kind=str(raw.get("kind") or "compute"),
            depends_on=list(raw.get("depends_on") or []),
            max_attempts=int(raw.get("max_attempts") or 3),
            attempt=int(raw.get("attempt") or 0),
            payload=dict(raw.get("payload") or {}),
            evidence=dict(raw.get("evidence") or {}),
            write_scopes=list(raw.get("write_scopes") or []),
            status=_STATUS[status] if status else NodeStatus.PENDING,
            error=raw.get("error"),
        )
        graph.add_node(node)
    for raw in spec.get("edges") or []:
        graph.add_dependency(
            DependencyEdge(
                from_node=str(raw["from"]),
                to_node=str(raw["to"]),
                types=list(raw.get("types") or ["control"]),
                reason=str(raw.get("reason") or "case"),
                evidence_ref=raw.get("evidence_ref"),
            )
        )
    return graph


def _scripted_handler(
    kind: str,
    script: dict[str, Any],
    log: CallLog,
) -> Callable[[GraphNode, GraphRunContext], NodeOutcome]:
    mode = str(script.get("mode") or "succeed")

    def handler(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        log.record(kind, node.id)
        call_n = log.by_kind[kind]
        if mode == "succeed":
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload=dict(script.get("payload") or {"ok": True}),
                evidence=dict(script.get("evidence") or {}),
            )
        if mode == "fail":
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error=str(script.get("error") or "failed"),
            )
        if mode == "fail_n_then_succeed":
            fail_n = int(script.get("fail_count") or 1)
            if call_n <= fail_n:
                return NodeOutcome(
                    status=NodeStatus.FAILED,
                    error=str(script.get("error") or "transient"),
                )
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload=dict(script.get("payload") or {"recovered": True}),
            )
        if mode == "raise":
            raise RuntimeError(str(script.get("message") or "boom"))
        if mode == "non_success_status":
            return NodeOutcome(
                status=_STATUS[str(script.get("status") or "running")],
                error=script.get("error"),
            )
        if mode == "succeed_from_parent":
            parent_id = str(script["parent"])
            field_name = str(script.get("field") or "value")
            parent = context.graph.nodes[parent_id]
            base = parent.payload.get(field_name, 0)
            out_field = str(script.get("out_field") or "sum")
            add = int(script.get("add") or 1)
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={out_field: int(base) + add},
            )
        if mode == "echo_id":
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={"done": node.id},
            )
        raise ValueError(f"unknown runner mode {mode!r} for kind {kind!r}")

    return handler


def build_registry(
    runners_spec: dict[str, Any] | None,
    log: CallLog,
) -> GraphNodeRunnerRegistry:
    registry = GraphNodeRunnerRegistry()
    for kind, script in (runners_spec or {}).items():
        grants = resolve_grants(script.get("grants"))
        registry.register(
            CallableGraphNodeRunner(
                [kind],
                _scripted_handler(kind, script, log),
                grants=grants,
            )
        )
    return registry


class _FixedFailurePolicy(GraphFailurePolicy):
    def __init__(self, action: GraphFailureAction) -> None:
        self._action = action

    def decide(self, node: GraphNode, *, error: str | None) -> GraphFailureAction:
        del node, error
        return self._action


def build_failure_policy(name: str | None) -> GraphFailurePolicy:
    key = (name or "default").lower()
    if key == "default":
        return DefaultGraphFailurePolicy()
    if key == "fail":
        return _FixedFailurePolicy(GraphFailureAction.FAIL)
    if key == "retry":
        return _FixedFailurePolicy(GraphFailureAction.RETRY)
    if key == "escalate":
        return _FixedFailurePolicy(GraphFailureAction.ESCALATE)
    raise ValueError(f"unknown failure_policy {name!r}")


class _HealEscalation(GraphEscalation):
    async def handle(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={**node.payload, "healed": True},
            evidence=dict(node.evidence),
        )


class _FailEscalation(GraphEscalation):
    async def handle(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.FAILED,
            error=node.error or "escalation_failed",
            payload=dict(node.payload),
        )


class _RetryEscalation(GraphEscalation):
    """Return a non-terminal status so the executor may re-queue (escalated_retry)."""

    async def handle(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.READY,
            payload={**node.payload, "escalation": "retry"},
            error=None,
        )


def build_escalation(name: str | None) -> GraphEscalation:
    key = (name or "reject").lower()
    if key == "reject":
        return RejectGraphEscalation()
    if key == "heal":
        return _HealEscalation()
    if key == "fail":
        return _FailEscalation()
    if key == "retry":
        return _RetryEscalation()
    raise ValueError(f"unknown escalation {name!r}")


class CaseConfig(MechaHarnessConfig):
    def __init__(
        self,
        *,
        runners: GraphNodeRunnerRegistry,
        grants: list[object],
        failure_policy: GraphFailurePolicy,
        escalation: GraphEscalation,
    ) -> None:
        self._runners = runners
        self._grants = grants
        self._failure_policy = failure_policy
        self._escalation = escalation
        super().__init__()  # type: ignore[no-untyped-call]

    def get_inference_class(self) -> type[InferenceStrategy]:
        return MockInferenceStrategy

    def get_harness_class(self) -> type[AbstractHarness]:
        return PassThroughHarness

    def get_harness_config(self) -> HarnessConfig:
        return HarnessConfig(model="mock", max_turns=1)

    def get_tools(self) -> ToolRegistry:
        return ToolRegistry()

    def get_grants(self) -> list[object]:
        return self._grants

    def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
        return self._runners

    def get_graph_failure_policy(self) -> GraphFailurePolicy:
        return self._failure_policy

    def get_graph_escalation(self) -> GraphEscalation:
        return self._escalation


def mutate_graph(graph: ExecutionGraph, mutations: dict[str, Any] | None) -> None:
    if not mutations:
        return
    for node_id, patch in (mutations.get("nodes") or {}).items():
        node = graph.nodes[node_id]
        if "status" in patch:
            node.status = _STATUS[str(patch["status"])]
        if "attempt" in patch:
            node.attempt = int(patch["attempt"])
        if patch.get("clear_payload"):
            node.payload = {}
        if "payload" in patch:
            node.payload = dict(patch["payload"])
        if "error" in patch:
            node.error = patch["error"]
        if "max_attempts" in patch:
            node.max_attempts = int(patch["max_attempts"])


def assert_expect(
    *,
    result: Any,
    expect: dict[str, Any],
    log: CallLog,
    case_id: str,
) -> None:
    prefix = f"case {case_id}"
    if "status" in expect:
        assert result.status == expect["status"], f"{prefix}: status"
    if "error" in expect:
        assert result.error == expect["error"], f"{prefix}: error"
    if "error_is_none" in expect:
        assert (result.error is None) is bool(expect["error_is_none"]), f"{prefix}: error_is_none"

    for node_id, node_exp in (expect.get("nodes") or {}).items():
        node = result.graph.nodes[node_id]
        if "status" in node_exp:
            assert node.status.value == node_exp["status"], f"{prefix}: node {node_id} status"
        if "attempt" in node_exp:
            assert node.attempt == node_exp["attempt"], f"{prefix}: node {node_id} attempt"
        if "error" in node_exp:
            assert node.error == node_exp["error"], f"{prefix}: node {node_id} error"
        if "error_contains" in node_exp:
            assert node.error and node_exp["error_contains"] in node.error, (
                f"{prefix}: node {node_id} error_contains"
            )
        for key, value in (node_exp.get("payload") or {}).items():
            assert node.payload.get(key) == value, f"{prefix}: node {node_id} payload.{key}"
        if "payload_missing" in node_exp:
            for key in node_exp["payload_missing"]:
                assert key not in node.payload, f"{prefix}: node {node_id} unexpected payload {key}"

    types = [e.type for e in result.events]
    for event_type in expect.get("events_include") or []:
        assert event_type in types, f"{prefix}: missing event {event_type} in {types}"
    for event_type in expect.get("events_exclude") or []:
        assert event_type not in types, f"{prefix}: unexpected event {event_type}"
    if "graph_end_count" in expect:
        end_count = types.count("core:graph_end")
        assert end_count == expect["graph_end_count"], f"{prefix}: graph_end_count"

    for kind, count in (expect.get("runner_calls") or {}).items():
        assert log.by_kind.get(kind, 0) == count, f"{prefix}: runner_calls[{kind}]"
    if "run_order" in expect:
        assert log.order == list(expect["run_order"]), f"{prefix}: run_order"
    if "run_order_includes" in expect:
        for node_id in expect["run_order_includes"]:
            assert node_id in log.order, f"{prefix}: run_order missing {node_id}"


def phases(case: GraphExecutorCase) -> Iterator[dict[str, Any]]:
    data = case.data
    if "phases" in data:
        yield from data["phases"]
        return
    yield {
        "run": data.get("run") or {},
        "expect": data.get("expect") or {},
        "mutate": data.get("mutate"),
    }
