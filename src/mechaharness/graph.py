"""Durable execution-graph primitives and verification (GRF-* / VER-*)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.events import CoreEvent, Event, EventLog, InMemoryEventLog, event_type_key


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str = "compute"
    goal: str = ""
    acceptance: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    attempt: int = 0
    max_attempts: int = 3
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class GraphEvent(CoreEvent):
    name = "graph_node"


class ExecutionGraph(BaseModel):
    """Minimal durable graph over EventLog (GRF-01/02/03)."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str = ""
    nodes: dict[str, GraphNode] = Field(default_factory=dict)

    def add_node(self, node: GraphNode) -> GraphNode:
        self.nodes[node.id] = node
        return node

    def ready_nodes(self) -> list[GraphNode]:
        ready: list[GraphNode] = []
        for node in self.nodes.values():
            if node.status not in {NodeStatus.PENDING, NodeStatus.READY, NodeStatus.FAILED}:
                continue
            if node.attempt >= node.max_attempts and node.status == NodeStatus.FAILED:
                continue
            deps_ok = all(
                self.nodes[d].status == NodeStatus.SUCCEEDED
                for d in node.depends_on
                if d in self.nodes
            )
            if deps_ok:
                if node.status == NodeStatus.PENDING:
                    node.status = NodeStatus.READY
                ready.append(node)
            elif node.status != NodeStatus.FAILED:
                node.status = NodeStatus.BLOCKED
        return ready

    def checkpoint(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def resume(cls, payload: Mapping[str, Any]) -> ExecutionGraph:
        return cls.model_validate(payload)


class GraphStore:
    """Persist graph checkpoints via EventLog payloads."""

    def __init__(self, event_log: EventLog | None = None, *, agent_id: str = "graph") -> None:
        self.event_log = event_log or InMemoryEventLog()
        self.agent_id = agent_id

    def save(self, graph: ExecutionGraph, *, run_id: str | None = None) -> None:
        rid = run_id or graph.id
        self.event_log.emit(
            Event(
                type=event_type_key(GraphEvent),
                agent_id=self.agent_id,
                run_id=rid,
                payload={"graph": graph.checkpoint()},
            )
        )

    def latest(self, *, run_id: str | None = None) -> ExecutionGraph | None:
        events = self.event_log.query(run_id=run_id, types=[GraphEvent])
        if not events:
            return None
        payload = events[-1].payload.get("graph")
        if not isinstance(payload, dict):
            return None
        return ExecutionGraph.resume(payload)


Verifier = Callable[[GraphNode], tuple[bool, dict[str, Any]]]


def verify_node(node: GraphNode, verifiers: Sequence[Verifier]) -> tuple[bool, dict[str, Any]]:
    """Run completion evidence checks (VER-01). Judge scores are supplementary."""
    evidence: dict[str, Any] = dict(node.evidence)
    for verifier in verifiers:
        ok, detail = verifier(node)
        evidence.update(detail)
        if not ok:
            return False, evidence
    return True, evidence


def bounded_repair(
    node: GraphNode,
    *,
    verifiers: Sequence[Verifier],
    repair: Callable[[GraphNode], GraphNode] | None = None,
) -> GraphNode:
    """verify → classify → permitted repair → retry (VER-03)."""
    while node.attempt < node.max_attempts:
        node.attempt += 1
        node.status = NodeStatus.RUNNING
        ok, evidence = verify_node(node, verifiers)
        node.evidence = evidence
        if ok:
            node.status = NodeStatus.SUCCEEDED
            node.error = None
            return node
        node.status = NodeStatus.FAILED
        node.error = "verification_failed"
        if repair is None:
            break
        node = repair(node)
    return node
