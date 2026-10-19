"""Neighbor revisit + checkpoint over write-scope conflicts (MH-SR-08)."""

from __future__ import annotations

import pytest

from mechaharness.decision_conflict_checkpoint import (
    neighbor_revisit,
    neighbors_from_write_conflicts,
)
from mechaharness.graph import ExecutionGraph, GraphNode

_REVISIT = [
    # id, resolved, neighbors, visited, revisit, skipped, checkpoint, cycle_blocked
    ("fresh_neighbors", "a", ["b", "c"], [], ["b", "c"], [], False, False),
    ("visited_neighbor_skipped", "a", ["b", "c"], ["b"], ["c"], ["b"], False, False),
    ("all_visited_is_cycle_blocked", "b", ["a"], ["a"], [], ["a"], False, True),
    ("no_conflicts_checkpoints", "c", [], ["a", "b"], [], [], True, False),
    ("duplicates_and_self_ignored", "a", ["b", "b", "a"], [], ["b"], [], False, False),
]


@pytest.mark.parametrize(
    ("case_id", "resolved", "neighbors", "visited", "revisit", "skipped", "ckpt", "cycle"),
    _REVISIT,
    ids=[c[0] for c in _REVISIT],
)
def test_neighbor_revisit(
    case_id, resolved, neighbors, visited, revisit, skipped, ckpt, cycle
) -> None:
    del case_id
    step = neighbor_revisit(resolved, neighbors, visited=set(visited))
    assert step.revisit == revisit
    assert step.skipped_visited == skipped
    assert step.checkpoint is ckpt
    assert step.cycle_blocked is cycle
    assert resolved in step.visited


def test_neighbors_come_from_concurrent_write_conflicts() -> None:
    graph = ExecutionGraph(goal="g")
    for node_id, scopes in {"a": ["repo:x"], "b": ["repo:x", "repo:y"], "c": ["repo:y"]}.items():
        graph.add_node(GraphNode(id=node_id, kind="k", write_scopes=scopes))
    conflicts = graph.concurrent_write_conflicts(["a", "b", "c"])
    assert neighbors_from_write_conflicts("b", conflicts) == ["a", "c"]
    assert neighbors_from_write_conflicts("a", conflicts) == ["b"]
    assert neighbors_from_write_conflicts("z", conflicts) == []


def test_a_cyclic_conflict_walk_terminates_with_a_checkpoint_only_when_cleared() -> None:
    adjacency = {"a": ["b"], "b": ["a", "c"], "c": ["b"]}
    visited: set[str] = set()
    queue = ["a"]
    order: list[str] = []
    checkpoints: list[str] = []
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        order.append(node)
        step = neighbor_revisit(node, adjacency[node], visited=visited)
        visited = set(step.visited)
        queue.extend(step.revisit)
        if step.checkpoint:
            checkpoints.append(node)
    assert order == ["a", "b", "c"]
    assert checkpoints == []  # every node still conflicts with a visited neighbor
