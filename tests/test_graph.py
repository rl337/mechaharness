"""Execution graph and verification tests."""

from __future__ import annotations

from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
    GraphStore,
    NodeStatus,
    bounded_repair,
)


def test_graph_checkpoint_resume_and_verification() -> None:
    graph = ExecutionGraph(goal="media render")
    n1 = graph.add_node(GraphNode(id="submit", kind="tool", acceptance=["prompt_id"]))
    n2 = graph.add_node(
        GraphNode(id="fetch", kind="tool", depends_on=["submit"], acceptance=["file"])
    )
    n1.status = NodeStatus.SUCCEEDED
    n1.evidence = {"prompt_id": "p1"}
    ready = graph.ready_nodes()
    assert any(n.id == "fetch" for n in ready)

    store = GraphStore()
    store.save(graph, run_id="r1")
    restored = store.latest(run_id="r1")
    assert restored is not None
    assert "fetch" in restored.nodes

    def has_file(node: GraphNode) -> tuple[bool, dict]:
        ok = bool(node.payload.get("path"))
        return ok, {"file": node.payload.get("path")}

    node = GraphNode(id="x", payload={})
    repaired = bounded_repair(
        node,
        verifiers=[has_file],
        repair=lambda n: n.model_copy(update={"payload": {"path": "/tmp/out.png"}}),
    )
    assert repaired.status == NodeStatus.SUCCEEDED
