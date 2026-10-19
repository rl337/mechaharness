"""Neighbor-revisit and checkpoint helpers over write-scope conflicts (MH-SR-08).

This is **not** a second conflict-resolution engine. The conflict facts still
come from :meth:`mechaharness.graph.ExecutionGraph.concurrent_write_conflicts`
(``"scope:a,b"`` strings) and the checkpoint still goes through
``CheckpointStore``. These pure functions only answer two questions after a
node is resolved:

1. Which conflicting neighbors must be revisited, without revisiting any node
   already visited in this pass (cycle prevention)?
2. Is the decision conflict-free, so the host should checkpoint now?

::

    >>> from mechaharness.decision_conflict_checkpoint import neighbor_revisit
    >>> step = neighbor_revisit("a", ["b", "c"], visited=set())
    >>> step.revisit, step.checkpoint
    (['b', 'c'], False)
    >>> neighbor_revisit("b", ["a"], visited={"a"}).cycle_blocked
    True
    >>> neighbor_revisit("c", [], visited={"a", "b"}).checkpoint
    True
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from pydantic import BaseModel, ConfigDict, Field


class NeighborRevisit(BaseModel):
    """What to do after one node was resolved."""

    model_config = ConfigDict(extra="allow")

    resolved: str
    revisit: list[str] = Field(default_factory=list)
    skipped_visited: list[str] = Field(default_factory=list)
    visited: list[str] = Field(default_factory=list)
    checkpoint: bool = False
    cycle_blocked: bool = False


def neighbors_from_write_conflicts(
    node_id: str, conflicts: Sequence[str]
) -> list[str]:
    """Neighbors of ``node_id`` in ``concurrent_write_conflicts`` output.

    Each conflict string is ``"<scope>:<id>,<id>,..."``; neighbors are the other
    ids that share a scope with ``node_id``, in first-seen order.
    """
    neighbors: list[str] = []
    for conflict in conflicts:
        _scope, _, ids = conflict.rpartition(":")
        members = [part for part in ids.split(",") if part]
        if node_id not in members:
            continue
        for member in members:
            if member != node_id and member not in neighbors:
                neighbors.append(member)
    return neighbors


def neighbor_revisit(
    resolved: str,
    conflict_neighbors: Sequence[str],
    *,
    visited: Collection[str],
) -> NeighborRevisit:
    """Next nodes to revisit after ``resolved``, and whether to checkpoint.

    ``conflict_neighbors`` are the nodes still in conflict with ``resolved``'s
    new decision. Already-visited neighbors are skipped, which is what stops a
    cycle from looping forever. ``checkpoint`` is true only when no conflicting
    neighbor remains at all (the decision cleared its conflicts); a conflict
    that is blocked only by the visited set reports ``cycle_blocked`` instead so
    the host can escalate rather than silently checkpoint a conflicted state.
    """
    seen = set(visited) | {resolved}
    revisit: list[str] = []
    skipped: list[str] = []
    for neighbor in conflict_neighbors:
        if neighbor == resolved or neighbor in revisit or neighbor in skipped:
            continue
        (skipped if neighbor in seen else revisit).append(neighbor)
    cleared = not revisit and not skipped
    return NeighborRevisit(
        resolved=resolved,
        revisit=revisit,
        skipped_visited=skipped,
        visited=sorted(seen),
        checkpoint=cleared,
        cycle_blocked=bool(skipped) and not revisit,
    )
