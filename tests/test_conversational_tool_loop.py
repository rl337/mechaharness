"""Tests for conversational_tool_loop recipe + runner (HF-07/HF-08)."""

from __future__ import annotations

import asyncio

from mechaharness.budget import BudgetPolicy
from mechaharness.conversational_tool_loop_runner import ConversationalToolLoopRunner
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_templates import (
    ConversationalToolLoopTemplate,
    GraphTemplateParams,
)
from mechaharness.host_kit import host_graph_executor, tapping_event_log
from mechaharness.node_component import embed_recipe_as_tool


def test_template_in_catalog() -> None:
    from mechaharness.graph_templates import default_graph_templates

    assert "conversational_tool_loop" in default_graph_templates().names()


def test_runner_expands_checkpoint_nesting() -> None:
    calls = {"n": 0}

    def complete(messages, meta):
        del messages, meta
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ],
            }
        return {"role": "assistant", "content": "done", "tool_calls": []}

    def dispatch(name, args):
        del args
        return f"ok:{name}"

    runner = ConversationalToolLoopRunner(complete=complete, dispatch_tool=dispatch)
    graph = ConversationalToolLoopTemplate().instantiate(
        GraphTemplateParams(goal="loop", inputs={"max_iterations": 4})
    )
    seen: list[str] = []
    log = tapping_event_log(on_event=lambda e: seen.append(str(getattr(e, "type", ""))))
    executor = host_graph_executor(runners=[runner], event_log=log)
    result = asyncio.run(
        executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            run_id="ctl-1",
            skip_linkage=True,
        )
    )
    assert result.status == "ok"
    tools = result.graph.nodes["tools"]
    assert tools.subgraph is not None
    child = ExecutionGraph.resume(tools.subgraph)
    node_ids = sorted(child.nodes)
    assert any(i.endswith("/inference") for i in node_ids)
    assert any("tool_call:lookup" in i for i in node_ids)
    assert any("graph_node_start" in t or t.endswith("graph_node_start") for t in seen)


def test_recipe_as_tool_nested_child_run() -> None:
    child = ExecutionGraph(goal="oneshot")
    child.add_node(GraphNode(id="prompt", kind="compute"))
    child.template_name = "oneshot"

    async def ok(node, context):
        del context
        return __import__(
            "mechaharness.graph_executor", fromlist=["NodeOutcome"]
        ).NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    from mechaharness.graph_executor import CallableGraphNodeRunner

    parent = ExecutionGraph(goal="parent")
    parent.add_node(
        embed_recipe_as_tool(child, parent_node_id="generate_image", tool_name="generate_image")
    )
    executor = host_graph_executor(
        runners=[CallableGraphNodeRunner(["compute"], ok)],
    )
    result = asyncio.run(
        executor.run(
            parent,
            budget_policy=BudgetPolicy.unlimited(),
            run_id="rat-1",
            skip_linkage=True,
        )
    )
    wrap = result.graph.nodes["generate_image"]
    assert result.status == "ok"
    assert wrap.payload.get("child_run_id")
    assert wrap.payload.get("child_status") == "ok"
