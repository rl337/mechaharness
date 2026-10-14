"""Unit tests for node_component query and traversal."""

from __future__ import annotations

from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.graph_templates import (
    ConversationalToolLoopTemplate,
    GraphTemplateParams,
    SubgraphNodeRunner,
)
from mechaharness.node_component import (
    NODE_COMPONENT_KINDS,
    embed_recipe_as_tool,
    node_components_for,
    node_components_for_harness,
    traversal_from_events,
)


def test_node_components_for_soft_points_and_stop() -> None:
    graph = ConversationalToolLoopTemplate().instantiate(
        GraphTemplateParams(goal="chat tools", inputs={"max_iterations": 3})
    )
    comps = node_components_for(graph, template=ConversationalToolLoopTemplate())
    assert comps
    assert all(c.parent_node_id for c in comps)
    assert all(c.kind in NODE_COMPONENT_KINDS for c in comps)
    kinds = {c.kind for c in comps}
    assert "stop_contract" in kinds
    assert "soft_point" in kinds


def test_node_components_for_child_graph() -> None:
    child = ExecutionGraph(goal="child")
    child.add_node(GraphNode(id="c1", kind="compute"))
    parent = ExecutionGraph(goal="parent")
    parent.add_node(SubgraphNodeRunner.embed(child, parent_node_id="wrap"))
    comps = node_components_for(parent)
    assert any(c.kind == "child_graph" and c.parent_node_id == "wrap" for c in comps)


def test_node_components_for_harness_tools() -> None:
    comps = node_components_for_harness(parent_node_id="harness", tool_names=["lookup"])
    kinds = {c.kind for c in comps}
    assert {"turn_start", "inference", "tool_call", "tool_result"} <= kinds
    assert all(c.parent_node_id == "harness" for c in comps)


def test_traversal_from_events_aligns_parent() -> None:
    events = [
        {
            "type": "core:inference",
            "payload": {
                "parent_node_id": "harness",
                "component_id": "harness/inference:1",
            },
        },
        {
            "type": "core:tool_call",
            "payload": {
                "tool_name": "lookup",
                "parent_node_id": "harness",
                "component_id": "harness/tool_call:lookup:1",
            },
        },
    ]
    records = traversal_from_events(events)
    assert len(records) == 2
    assert records[0].kind == "inference"
    assert records[0].parent_node_id == "harness"
    assert records[1].kind == "tool_call"


def test_embed_recipe_as_tool_sets_subgraph() -> None:
    child = ExecutionGraph(goal="image")
    child.add_node(GraphNode(id="prompt", kind="compute"))
    child.template_name = "oneshot"
    node = embed_recipe_as_tool(child, parent_node_id="generate_image", tool_name="generate_image")
    assert node.kind == "tool_call"
    assert node.subgraph is not None
    assert node.payload.get("recipe_as_tool") is True
