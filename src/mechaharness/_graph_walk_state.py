"""Private graph-state transitions and frame bag bindings.

These functions mutate only the supplied graph or bag. Authorization, budget,
effect dispatch, cancellation policy, checkpointing, and events stay in GraphExecutor.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from mechaharness.core.exceptions import GraphExecutorError
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.walk_bag import WalkBag


def terminal_status(graph: ExecutionGraph) -> Literal["ok", "failed", "stalled", "soft_exhausted"]:
    statuses = {n.status for n in graph.nodes.values()}
    if statuses and statuses <= {NodeStatus.SUCCEEDED}:
        return "ok"
    if statuses and statuses <= {NodeStatus.SUCCEEDED, NodeStatus.CANCELLED}:
        if NodeStatus.CANCELLED in statuses:
            return "soft_exhausted"
        return "ok"
    if any(n.status == NodeStatus.FAILED for n in graph.nodes.values()):
        if not graph.ready_nodes():
            return "failed"
    if graph.ready_nodes():
        return "stalled"
    active = {
        NodeStatus.PENDING,
        NodeStatus.READY,
        NodeStatus.BLOCKED,
        NodeStatus.RUNNING,
    }
    if any(n.status in active for n in graph.nodes.values()):
        return "stalled"
    return "failed"


def cancel_open_nodes(graph: ExecutionGraph, *, reason: str) -> None:
    open_statuses = {
        NodeStatus.PENDING,
        NodeStatus.READY,
        NodeStatus.BLOCKED,
    }
    for node in graph.nodes.values():
        if node.status in open_statuses:
            node.status = NodeStatus.CANCELLED
            node.error = reason


def fail_open_nodes(graph: ExecutionGraph, *, reason: str) -> None:
    open_statuses = {
        NodeStatus.PENDING,
        NodeStatus.READY,
        NodeStatus.BLOCKED,
        NodeStatus.RUNNING,
    }
    for node in graph.nodes.values():
        if node.status in open_statuses:
            node.status = NodeStatus.FAILED
            node.error = reason


def bag_path_bindings(node: GraphNode, key: str) -> dict[str, str]:
    """``payload.bag_inputs`` / ``bag_outputs``: dest_path → source_path."""
    raw = node.payload.get(key)
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise GraphExecutorError(f"node {node.id!r} payload.{key} must be a mapping")
    return {str(dest): str(src) for dest, src in raw.items()}


def project_child_bag(node: GraphNode, parent_bag: WalkBag) -> WalkBag:
    """Child bag from declared ``bag_inputs`` (empty when unbound — no share)."""
    return WalkBag.project_from(parent_bag, bindings=bag_path_bindings(node, "bag_inputs"))


def merge_child_bag_outputs(
    node: GraphNode,
    parent_bag: WalkBag,
    child_graph: ExecutionGraph,
) -> None:
    """Copy declared ``bag_outputs`` from child checkpoint into the parent bag."""
    bindings = bag_path_bindings(node, "bag_outputs")
    if not bindings:
        return
    child_bag = WalkBag.deserialize(child_graph.walk_bag)
    parent_bag.merge_from(child_bag, bindings=bindings)
