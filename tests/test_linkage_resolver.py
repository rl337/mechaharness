"""Data-driven cases for linkage resolution, envelopes, and stop contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import AccessPolicy, InMemoryAccessControl
from mechaharness.core.environment import NoOpInferenceEnvironment
from mechaharness.core.events import InMemoryEventLog
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphNodeRunnerRegistry,
    NodeOutcome,
)
from mechaharness.linkage_resolver import DefaultLinkageResolver
from mechaharness.stop_contract import StopContract

CASES_DIR = Path(__file__).resolve().parent / "fixtures" / "linkage_resolver"


def iter_cases() -> list[dict[str, Any]]:
    if not CASES_DIR.is_dir():
        return []
    cases = []
    for path in sorted(CASES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("id", path.stem)
        cases.append(data)
    return cases


def _registry(kinds: list[str]) -> GraphNodeRunnerRegistry:
    reg = GraphNodeRunnerRegistry()

    async def ok(node: GraphNode, *, context: Any) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    for kind in kinds:
        # CallableGraphNodeRunner passes context positionally.
        async def _handler(node: GraphNode, context: Any, _kind: str = kind) -> NodeOutcome:
            del context, _kind
            return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

        reg.register(CallableGraphNodeRunner([kind], _handler))
    return reg


@pytest.mark.parametrize("case", iter_cases(), ids=lambda c: c["id"])
def test_linkage_resolver_cases(case: dict[str, Any]) -> None:
    assert iter_cases(), "expected linkage_resolver fixtures"
    grants = case.get("grants") or ["core:graph.execute"]
    access = InMemoryAccessControl(
        event_log=InMemoryEventLog(),
        policy=AccessPolicy(grants=grants),
    )
    runners = _registry(list(case.get("runner_kinds") or ["compute"]))
    resolver = DefaultLinkageResolver(
        runners=runners,
        access=access,
        environment=NoOpInferenceEnvironment(),
    )
    graph = ExecutionGraph(goal=case.get("goal") or "t", version=str(case.get("version") or "1"))
    for raw in case.get("nodes") or []:
        stop = raw.get("stop_contract")
        graph.add_node(
            GraphNode(
                id=str(raw["id"]),
                kind=str(raw.get("kind") or "compute"),
                depends_on=list(raw.get("depends_on") or []),
                repeating=bool(raw.get("repeating") or False),
                stop_contract=stop,
                payload=dict(raw.get("payload") or {}),
            )
        )
    envelope = None
    if case.get("envelope"):
        envelope = CapabilityEnvelope.model_validate(case["envelope"])
    report = resolver.resolve(graph, envelope=envelope)
    expect = case["expect"]
    assert report.ok is expect["ok"]
    codes = [e.code for e in report.edges]
    for code in expect.get("codes_include") or []:
        assert code in codes
    for code in expect.get("codes_exclude") or []:
        assert code not in codes
    if expect.get("has_fingerprint"):
        assert report.fingerprint


def test_stop_contract_round_trip() -> None:
    stop = StopContract(version="2", max_iterations=4, trigger="schedule")
    guard = stop.guard()
    assert guard.contract.max_iterations == 4
    again = StopContract.from_convergence(stop.to_convergence(), trigger="schedule")
    assert again.max_iterations == 4


def test_capability_envelope_narrow_rejects_widen() -> None:
    parent = CapabilityEnvelope(grants=["core:graph.execute"], tool_names=["echo"])
    child = parent.narrow(grants=["core:graph.execute"], tool_names=[])
    assert child.tool_names == []
    with pytest.raises(ValueError, match="widens"):
        parent.narrow(grants=["core:graph.execute", "core:fs.write"])
