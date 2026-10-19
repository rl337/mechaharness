"""Pre-effect authority revalidation and its GraphExecutor wiring (MH-DOTS-02)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pyiv import get_injector

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import GraphExecute
from mechaharness.di import MechaHarnessConfig
from mechaharness.effect_revalidation import revalidate_before_effect
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphExecutor,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)

_FUNCTION_CASES = [
    ("no_envelope", {}, True, None),
    ("fresh", {"envelope": {"authorization_epoch": 1}, "live_authorization_epoch": 1}, True, None),
    ("expired", {"envelope": {"expires_at": "2026-10-18T11:00:00Z"}}, False, "envelope_expired"),
    (
        "epoch_advanced",
        {"envelope": {"authorization_epoch": 1}, "live_authorization_epoch": 2},
        False,
        "authorization_epoch_advanced:1!=2",
    ),
    (
        "grant_missing",
        {"envelope": {"grants": ["core:fs.read"]}, "required_grants": ["core:net.http"]},
        False,
        "envelope_grant_missing:core:net.http",
    ),
    ("access_revoked", {"access_allows": lambda _g: False}, False, "access_revoked"),
]


@pytest.mark.parametrize(
    ("case_id", "kwargs", "ok", "reason"), _FUNCTION_CASES, ids=[c[0] for c in _FUNCTION_CASES]
)
def test_revalidate_before_effect(case_id: str, kwargs: dict, ok: bool, reason: str | None) -> None:
    del case_id
    kwargs = dict(kwargs)
    if "envelope" in kwargs:
        kwargs["envelope"] = CapabilityEnvelope(**kwargs["envelope"])
    result = revalidate_before_effect(now=NOW, **kwargs)
    assert (result.ok, result.reason) == (ok, reason)


def _executor(calls: list[str]) -> GraphExecutor:
    async def work(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        calls.append(node.id)
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], work)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    return get_injector(Cfg()).inject(GraphExecutor)


_EXECUTOR_CASES = [
    # id, node payload, envelope kwargs, live epoch, expect runner called
    ("execute_fresh", {}, {"authorization_epoch": 1}, 1, True),
    ("execute_epoch_advanced", {}, {"authorization_epoch": 1}, 2, False),
    ("execute_expired", {}, {"expires_at": "2000-01-01T00:00:00Z"}, None, False),
    (
        "observe_skips_revalidation",
        {"tool_phase": "observe"},
        {"expires_at": "2000-01-01T00:00:00Z"},
        None,
        True,
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_id", "payload", "env", "live", "called"),
    _EXECUTOR_CASES,
    ids=[c[0] for c in _EXECUTOR_CASES],
)
async def test_executor_revalidates_execute_phase_nodes(
    case_id: str, payload: dict, env: dict, live: int | None, called: bool
) -> None:
    del case_id
    calls: list[str] = []
    executor = _executor(calls)
    if live is not None:
        executor.live_authorization_epoch = lambda: live
    graph = ExecutionGraph(goal="effect")
    graph.add_node(GraphNode(id="n", kind="compute", payload=payload))
    result = await executor.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        envelope=CapabilityEnvelope(grants=["core:graph.execute"], **env),
    )
    assert (calls == ["n"]) is called
    if not called:
        assert result.status == "failed"
        assert graph.nodes["n"].error.startswith("revalidation_failed:")
