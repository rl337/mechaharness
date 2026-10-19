"""Concrete CLI capability graph (not a GraphTemplate).

Hand-built :class:`~mechaharness.graph.ExecutionGraph` that grows as the host
CLI gains verbs. Wave 1: a single ``infer`` node (``cli:infer``).

See ``docs/reference/cli-universe.md``.
"""

from __future__ import annotations

from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus

CLI_INFER_KIND = "cli:infer"
CLI_INFER_NODE_ID = "infer"


def build_cli_universe_graph(*, prompt: str, system: str = "") -> ExecutionGraph:
    """Return a one-node graph that performs a reason-lane completion."""
    graph = ExecutionGraph(goal="cli_universe", version="1")
    graph.add_node(
        GraphNode(
            id=CLI_INFER_NODE_ID,
            kind=CLI_INFER_KIND,
            goal="one-shot inference",
            status=NodeStatus.PENDING,
            payload={"prompt": prompt, "system": system},
        )
    )
    return graph
