"""Observed execution topology distinct from intended graphs (MH-MHRL-03).

FineEnvs reconstructs model-call topology where retries become siblings and
subagents/compaction can become roots
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#from-calls-to-training-sequences).

MechaHarness exposes a ``RolloutGraph`` built from EventLog / graph runtime
records, optionally linked back to intended ``ExecutionGraph`` nodes::

    >>> from mechaharness.rollout_graph import RolloutGraph, RolloutNode, build_rollout_graph
    >>> g = build_rollout_graph([
    ...     {"id": "root", "kind": "model_call", "parent_id": None},
    ...     {"id": "retry", "kind": "retry", "parent_id": "root",
    ...      "execution_node_id": "produce", "attempt": 2},
    ...     {"id": "review", "kind": "delegated_agent", "parent_id": None},
    ... ])
    >>> sorted(g.roots())
    ['review', 'root']
    >>> g.nodes["retry"].execution_node_id
    'produce'
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RolloutNode(BaseModel):
    """One observed runtime node (model/tool/retry/subgraph/terminal/...)."""

    model_config = ConfigDict(extra="allow")

    id: str
    kind: str
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)
    execution_graph_id: str | None = None
    execution_node_id: str | None = None
    attempt: int | None = None
    status: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class RolloutGraph(BaseModel):
    """Observed runtime topology for one run (or shard)."""

    model_config = ConfigDict(extra="allow")

    run_id: str | None = None
    execution_graph_id: str | None = None
    nodes: dict[str, RolloutNode] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)

    def roots(self) -> list[str]:
        return sorted(n.id for n in self.nodes.values() if not n.parent_id)

    def link_execution(self, node_id: str, *, execution_node_id: str, attempt: int | None = None) -> None:
        node = self.nodes[node_id]
        node.execution_node_id = execution_node_id
        if attempt is not None:
            node.attempt = attempt


def build_rollout_graph(
    records: Sequence[Mapping[str, Any]],
    *,
    run_id: str | None = None,
    execution_graph_id: str | None = None,
) -> RolloutGraph:
    """Build a rollout graph from observed node records."""
    nodes: dict[str, RolloutNode] = {}
    for raw in records:
        node = RolloutNode.model_validate(raw)
        nodes[node.id] = node
    for node in nodes.values():
        if node.parent_id and node.parent_id in nodes:
            parent = nodes[node.parent_id]
            if node.id not in parent.children:
                parent.children.append(node.id)
    return RolloutGraph(
        run_id=run_id,
        execution_graph_id=execution_graph_id,
        nodes=nodes,
    )


def rollout_from_events(
    events: Sequence[Mapping[str, Any]],
    *,
    run_id: str | None = None,
    execution_graph_id: str | None = None,
) -> RolloutGraph:
    """Project EventLog-like payloads into a RolloutGraph.

    Recognizes common event type suffixes; unknown events are skipped.
    """
    records: list[dict[str, Any]] = []
    for idx, event in enumerate(events):
        etype = str(event.get("type") or event.get("event_type") or "")
        payload = dict(event.get("payload") or {})
        node_id = str(payload.get("node_id") or payload.get("id") or f"evt-{idx}")
        parent_id = payload.get("parent_id") or payload.get("parent_node_id")
        kind = "observation"
        if "inference" in etype:
            kind = "model_call"
        elif "tool" in etype:
            kind = "tool_call"
        elif "retry" in etype or payload.get("attempt", 1) not in (None, 0, 1):
            kind = "retry"
        elif "subgraph" in etype or payload.get("child_run_id"):
            kind = "dynamic_subgraph"
        elif "cancel" in etype:
            kind = "cancellation"
        elif "escalat" in etype:
            kind = "escalation"
        elif "compact" in etype or "context" in etype:
            kind = "context_transform"
        elif "subagent" in etype or payload.get("delegated"):
            kind = "delegated_agent"
        elif "end" in etype or payload.get("terminal"):
            kind = "terminal"
        records.append(
            {
                "id": node_id,
                "kind": kind,
                "parent_id": parent_id,
                "execution_node_id": payload.get("execution_node_id") or payload.get("graph_node_id"),
                "attempt": payload.get("attempt"),
                "status": payload.get("status"),
                "detail": payload,
            }
        )
    return build_rollout_graph(
        records, run_id=run_id, execution_graph_id=execution_graph_id
    )
