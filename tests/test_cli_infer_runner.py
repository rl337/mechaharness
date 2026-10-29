"""CliInferRunner legacy prompt + bag-aware ContextSpec paths."""

from __future__ import annotations

import pytest

from mechaharness.budget import Budget, BudgetPolicy
from mechaharness.cli_infer_runner import CliInferRunner, NodeScriptedCompleter
from mechaharness.core.access import InMemoryCostAccountant
from mechaharness.core.events import InMemoryEventLog
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    Usage,
)
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import GraphRunContext
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.walk_bag import WalkBag


def _ctx(*, bag: WalkBag | None = None) -> GraphRunContext:
    return GraphRunContext(
        graph=ExecutionGraph(goal="t"),
        run_id="r1",
        agent_id="a",
        budget=Budget(BudgetPolicy.unlimited()),
        bag=bag if bag is not None else WalkBag(),
    )


class _FixedCompleter(MockInferenceStrategy):
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            message=ChatMessage(
                role=Role.ASSISTANT,
                content='{"status":"found","files":["calc.py"]}',
            ),
            finish_reason="stop",
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


@pytest.mark.asyncio
async def test_legacy_prompt_still_works() -> None:
    log = InMemoryEventLog()
    runner = CliInferRunner(MockInferenceStrategy(), InMemoryCostAccountant(log), log)
    node = GraphNode(id="infer", kind="cli:infer", payload={"prompt": "hello"})
    outcome = await runner.run(node, context=_ctx())
    assert outcome.status == NodeStatus.SUCCEEDED
    assert "mock reply: hello" in str(outcome.payload.get("text"))


@pytest.mark.asyncio
async def test_bag_aware_compiles_and_publishes() -> None:
    log = InMemoryEventLog()
    completer = _FixedCompleter()
    runner = CliInferRunner(
        completer, InMemoryCostAccountant(log), log, kinds=["infer", "cli:infer"]
    )
    bag = WalkBag()
    bag.path_put("in.goal", "calc")
    node = GraphNode(
        id="discover",
        kind="infer",
        payload={
            "context": {
                "reads": [{"path": "in.goal", "required": True}],
                "system": "Discover files. Reply JSON only.",
                "response": {"writes": "out.discovery", "parse": "json"},
            }
        },
    )
    outcome = await runner.run(node, context=_ctx(bag=bag))
    assert outcome.status == NodeStatus.SUCCEEDED
    assert bag.path_get("out.discovery") == {"status": "found", "files": ["calc.py"]}
    assert "discover" in runner.last_model_inputs
    assert runner.last_model_inputs["discover"]["included_paths"] == ["in.goal"]
    assert "calc" in runner.last_model_inputs["discover"]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_scripted_completer_keys_by_node_id() -> None:
    log = InMemoryEventLog()
    scripted = NodeScriptedCompleter(
        {"plan": '{"plan":"ok"}'},
        MockInferenceStrategy(),
    )
    runner = CliInferRunner(scripted, InMemoryCostAccountant(log), log, kinds=["infer"])
    bag = WalkBag()
    bag.path_put("in.goal", "g")
    bag.path_put("out.verified", {"ok": True})
    bag.path_put("ctx.noise", {"secret": "x"})
    node = GraphNode(
        id="plan",
        kind="infer",
        payload={
            "context": {
                "reads": [
                    {"path": "in.goal"},
                    {"path": "out.verified"},
                ],
                "response": {"writes": "out.plan", "parse": "json"},
            }
        },
    )
    outcome = await runner.run(node, context=_ctx(bag=bag))
    assert outcome.status == NodeStatus.SUCCEEDED
    assert bag.path_get("out.plan") == {"plan": "ok"}
    inputs = runner.last_model_inputs["plan"]
    assert inputs["includes_verified_discovery"] is True
    assert inputs["includes_unrelated_bag_data"] is False
