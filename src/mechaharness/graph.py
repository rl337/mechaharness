"""Durable execution-graph primitives and verification (GRF-* / VER-*)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from typing import Any, Literal, cast
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


DependencyType = Literal["data", "state", "control", "resource"]
OracleStrength = Literal[
    "executable",
    "schema",
    "checksum",
    "external_observation",
    "model_judgment",
]
RecoveryBoundary = Literal[
    "planning",
    "dispatch",
    "post_effect_pre_record",
    "reduce",
    "commit",
]


class DependencyEdge(BaseModel):
    """Justified execution dependency (GRF-05)."""

    model_config = ConfigDict(extra="allow")

    from_node: str
    to_node: str
    types: list[DependencyType] = Field(default_factory=list)
    reason: str
    evidence_ref: str | None = None


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
    contract_version: str | None = None
    state_revision: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    write_scopes: list[str] = Field(default_factory=list)
    base_revision: str | None = None
    recovery_boundary: RecoveryBoundary | None = None


class GraphEvent(CoreEvent):
    name = "graph_node"


class ExecutionGraph(BaseModel):
    """Minimal durable graph over EventLog (GRF-01/02/03)."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str = ""
    nodes: dict[str, GraphNode] = Field(default_factory=dict)
    edges: list[DependencyEdge] = Field(default_factory=list)
    version: str = "1"

    def add_node(self, node: GraphNode) -> GraphNode:
        self.nodes[node.id] = node
        return node

    def add_dependency(self, edge: DependencyEdge) -> DependencyEdge:
        if not edge.types or not edge.reason:
            raise ValueError("dependency must declare types and reason")
        if edge.to_node not in self.nodes:
            raise KeyError(edge.to_node)
        if edge.from_node not in self.nodes:
            raise KeyError(edge.from_node)
        self.edges.append(edge)
        if edge.from_node not in self.nodes[edge.to_node].depends_on:
            self.nodes[edge.to_node].depends_on.append(edge.from_node)
        return edge

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

    def concurrent_write_conflicts(self, node_ids: Sequence[str]) -> list[str]:
        """Detect write/write conflicts among candidate parallel nodes (GRF-04)."""
        scopes: dict[str, list[str]] = {}
        for nid in node_ids:
            node = self.nodes[nid]
            for scope in node.write_scopes:
                scopes.setdefault(scope, []).append(nid)
        return [f"{scope}:{','.join(ids)}" for scope, ids in scopes.items() if len(ids) > 1]

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

    def save(
        self,
        graph: ExecutionGraph,
        *,
        run_id: str | None = None,
        boundary: RecoveryBoundary | None = None,
    ) -> None:
        rid = run_id or graph.id
        payload: dict[str, Any] = {"graph": graph.checkpoint()}
        if boundary is not None:
            payload["recovery_boundary"] = boundary
        self.event_log.emit(
            Event(
                type=event_type_key(GraphEvent),
                agent_id=self.agent_id,
                run_id=rid,
                payload=payload,
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

    def latest_boundary(self, *, run_id: str | None = None) -> RecoveryBoundary | None:
        events = self.event_log.query(run_id=run_id, types=[GraphEvent])
        if not events:
            return None
        boundary = events[-1].payload.get("recovery_boundary")
        allowed: frozenset[RecoveryBoundary] = frozenset(
            {
                "planning",
                "dispatch",
                "post_effect_pre_record",
                "reduce",
                "commit",
            }
        )
        if isinstance(boundary, str) and boundary in allowed:
            return cast(RecoveryBoundary, boundary)
        return None


Verifier = Callable[[GraphNode], tuple[bool, dict[str, Any]]]
VerifierResult = Literal["pass", "fail", "unknown"]


class VerificationOracle(BaseModel):
    """Claim-specific verification oracle with coverage notes (VER-01)."""

    model_config = ConfigDict(extra="allow")

    name: str
    strength: OracleStrength
    coverage: str = ""
    limitations: str = ""
    version: str = "1"


def select_strongest_oracle(
    oracles: Sequence[VerificationOracle],
) -> VerificationOracle | None:
    order = {
        "executable": 5,
        "external_observation": 4,
        "schema": 3,
        "checksum": 2,
        "model_judgment": 1,
    }
    if not oracles:
        return None
    return max(oracles, key=lambda o: order.get(o.strength, 0))


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


class ValidatorQualification(BaseModel):
    """VER-04: qualify validators against known-good/bad fixtures."""

    model_config = ConfigDict(extra="allow")

    verifier_version: str
    expected: VerifierResult
    observed: VerifierResult
    detection_gaps: list[str] = Field(default_factory=list)


def qualify_validator(
    *,
    name: str,
    verifier: Callable[[Any], VerifierResult],
    good_fixtures: Sequence[Any],
    bad_fixtures: Sequence[Any],
    missing_fixtures: Sequence[Any] | None = None,
    version: str = "1",
) -> list[ValidatorQualification]:
    """Reject always-pass validators; require bad fixtures to fail."""
    results: list[ValidatorQualification] = []
    for item in good_fixtures:
        observed = verifier(item)
        results.append(
            ValidatorQualification(
                verifier_version=version,
                expected="pass",
                observed=observed,
                detection_gaps=[] if observed == "pass" else [f"{name}:good_miss"],
            )
        )
    for item in bad_fixtures:
        observed = verifier(item)
        results.append(
            ValidatorQualification(
                verifier_version=version,
                expected="fail",
                observed=observed,
                detection_gaps=[] if observed == "fail" else [f"{name}:bad_undetected"],
            )
        )
    for item in missing_fixtures or []:
        observed = verifier(item)
        results.append(
            ValidatorQualification(
                verifier_version=version,
                expected="unknown",
                observed=observed,
                detection_gaps=[] if observed == "unknown" else [f"{name}:missing_not_unknown"],
            )
        )
    if bad_fixtures and all(r.observed == "pass" for r in results):
        results.append(
            ValidatorQualification(
                verifier_version=version,
                expected="fail",
                observed="pass",
                detection_gaps=[f"{name}:always_pass"],
            )
        )
    return results


def validator_qualified(results: Sequence[ValidatorQualification]) -> bool:
    return all(r.expected == r.observed and not r.detection_gaps for r in results)


class FanInItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    source_ref: str
    payload: dict[str, Any] = Field(default_factory=dict)
    failed: bool = False
    conflict: bool = False


class FanInResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: list[FanInItem] = Field(default_factory=list)
    duplicates_collapsed: int = 0
    conflicts: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)
    truncated: bool = False


def hierarchical_fan_in(
    branches: Sequence[FanInItem],
    *,
    budget: int,
    identity_key: str = "id",
) -> FanInResult:
    """Deterministic reduce with provenance (GRF-06)."""
    seen: dict[str, FanInItem] = {}
    duplicates = 0
    conflicts: list[str] = []
    failures: list[str] = []
    lineage: list[str] = []
    for item in branches:
        lineage.append(item.source_ref)
        key = str(item.payload.get(identity_key, item.id))
        if item.failed:
            failures.append(item.id)
        if item.conflict:
            conflicts.append(item.id)
        if key in seen:
            duplicates += 1
            continue
        seen[key] = item
    selected = list(seen.values())
    truncated = False
    if len(selected) > budget:
        selected = selected[:budget]
        truncated = True
    return FanInResult(
        items=selected,
        duplicates_collapsed=duplicates,
        conflicts=conflicts,
        failures=failures,
        lineage=lineage,
        truncated=truncated,
    )


def merge_branch_artifacts(
    *,
    base_revision: str,
    branches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply explicit conflict policy for parallel edits (GRF-04)."""
    merged: dict[str, Any] = {"base_revision": base_revision, "artifacts": {}, "conflicts": []}
    for branch in branches:
        path = str(branch.get("path", ""))
        content = branch.get("content")
        status = branch.get("status", "ok")
        if status != "ok":
            continue
        if path in merged["artifacts"] and merged["artifacts"][path] != content:
            merged["conflicts"].append(path)
        else:
            merged["artifacts"][path] = content
    return merged
