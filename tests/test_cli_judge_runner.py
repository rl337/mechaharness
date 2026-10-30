"""CliJudgeRunner: bag ContextSpec, zero tools, typed verdict."""

from __future__ import annotations

import pytest

from mechaharness.budget import Budget, BudgetPolicy
from mechaharness.cli_infer_runner import NodeScriptedCompleter
from mechaharness.cli_judge_runner import CliJudgeRunner
from mechaharness.core.access import InMemoryCostAccountant
from mechaharness.core.events import InMemoryEventLog
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import GraphRunContext
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.walk_bag import WalkBag


def _ctx(bag: WalkBag) -> GraphRunContext:
    return GraphRunContext(
        graph=ExecutionGraph(goal="j"),
        run_id="r",
        agent_id="a",
        budget=Budget(BudgetPolicy.unlimited()),
        bag=bag,
    )


@pytest.mark.asyncio
async def test_judge_publishes_verdict_without_tools() -> None:
    log = InMemoryEventLog()
    completer = NodeScriptedCompleter(
        {"judge": '{"valid": true, "verdict": "accept"}'},
        MockInferenceStrategy(),
    )
    runner = CliJudgeRunner(completer, InMemoryCostAccountant(log), log)
    bag = WalkBag()
    bag.path_put("out.proposal", {"action": "x"})
    bag.path_put("out.verified", {"ok": True})
    node = GraphNode(
        id="judge",
        kind="judge",
        payload={
            "context": {
                "reads": [
                    {"path": "out.proposal"},
                    {"path": "out.verified"},
                ],
                "response": {"writes": "out.judgment", "parse": "json"},
            }
        },
    )
    outcome = await runner.run(node, context=_ctx(bag))
    assert outcome.status == NodeStatus.SUCCEEDED
    assert bag.path_get("out.judgment")["valid"] is True
    assert runner.last_inference["judge"]["tool_call_count"] == 0
    assert runner.last_model_inputs["judge"]["tool_definitions"] == []
    assert runner.last_requests["judge"].tools is None


@pytest.mark.asyncio
async def test_judge_rejects_invalid_verdict() -> None:
    log = InMemoryEventLog()
    completer = NodeScriptedCompleter(
        {"judge": '{"maybe": true}'},
        MockInferenceStrategy(),
    )
    runner = CliJudgeRunner(completer, InMemoryCostAccountant(log), log)
    bag = WalkBag()
    bag.path_put("out.proposal", {"action": "x"})
    node = GraphNode(
        id="judge",
        kind="judge",
        payload={
            "context": {
                "reads": [{"path": "out.proposal"}],
                "response": {"writes": "out.judgment", "parse": "json"},
            }
        },
    )
    outcome = await runner.run(node, context=_ctx(bag))
    assert outcome.status == NodeStatus.FAILED
    assert outcome.error == "cli_judge_invalid_verdict"
