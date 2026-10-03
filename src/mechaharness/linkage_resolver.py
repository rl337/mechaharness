"""Pre-execution linkage resolution for runtime-composed graphs.

Primitive DI (pyiv) validates that injectables can be constructed. Linkage
resolution separately validates that the final graph has satisfiable runners,
grants, operation contracts, stop contracts, envelopes, environment
capabilities, and termination paths — before substantive execution.

Dynamic workflows stay intentionally partial until bind time; linkage is the
gate that fails with structured edges instead of a mid-run surprise::

    >>> from mechaharness.core.access import (
    ...     AccessPolicy, GraphExecute, InMemoryAccessControl,
    ... )
    >>> from mechaharness.core.environment import NoOpInferenceEnvironment
    >>> from mechaharness.core.events import InMemoryEventLog
    >>> from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
    >>> from mechaharness.graph_executor import (
    ...     CallableGraphNodeRunner, GraphNodeRunnerRegistry, NodeOutcome,
    ... )
    >>> from mechaharness.linkage_resolver import DefaultLinkageResolver
    >>> from mechaharness.stop_contract import StopContract
    >>> reg = GraphNodeRunnerRegistry()
    >>> async def ok(node, context):
    ...     return NodeOutcome(status=NodeStatus.SUCCEEDED)
    >>> reg.register(CallableGraphNodeRunner(["compute", "repair"], ok))
    >>> access = InMemoryAccessControl(
    ...     InMemoryEventLog(), AccessPolicy(grants=[GraphExecute]),
    ... )
    >>> resolver = DefaultLinkageResolver(
    ...     reg, access, NoOpInferenceEnvironment(),
    ... )
    >>> graph = ExecutionGraph(goal="ready")
    >>> _ = graph.add_node(GraphNode(
    ...     id="repair", kind="repair", repeating=True,
    ...     stop_contract=StopContract(max_iterations=3).model_dump(mode="json"),
    ... ))
    >>> resolver.resolve(graph).ok
    True
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import AccessControl, GraphExecute, grant_key
from mechaharness.core.environment import InferenceEnvironment
from mechaharness.core.exceptions import MechaHarnessError
from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.operation_registry import OperationRegistry
from mechaharness.stop_contract import StopContract


class RunnerRegistryLike(Protocol):
    """Minimal runner lookup used by linkage (avoids importing graph_executor)."""

    def get(self, kind: str) -> Any: ...

    def kinds(self) -> list[str]: ...


class LinkageError(MechaHarnessError):
    """Graph linkage failed before execution."""


class UnsatisfiedEdge(BaseModel):
    """One missing or incompatible linkage edge."""

    model_config = ConfigDict(extra="allow")

    code: str
    message: str
    node_id: str | None = None
    kind: str | None = None
    candidate_provider: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class LinkageReport(BaseModel):
    """Result of :meth:`LinkageResolver.resolve`."""

    model_config = ConfigDict(extra="allow")

    ok: bool = True
    edges: list[UnsatisfiedEdge] = Field(default_factory=list)
    fingerprint: str | None = None

    def raise_if_failed(self) -> None:
        if self.ok:
            return
        summary = "; ".join(f"{e.code}:{e.message}" for e in self.edges[:8])
        raise LinkageError(summary or "linkage_failed")


class LinkageResolver(ABC):
    """Validate final runtime graph wiring and substrate capabilities."""

    @abstractmethod
    def resolve(
        self,
        graph: ExecutionGraph,
        *,
        envelope: CapabilityEnvelope | None = None,
        fingerprint_parts: Mapping[str, Any] | None = None,
    ) -> LinkageReport:
        """Return a report; hosts may call ``raise_if_failed``."""


def stop_contract_from_node(node: GraphNode) -> StopContract | None:
    """Parse an optional stop contract from node fields / payload."""
    raw = getattr(node, "stop_contract", None)
    if raw is None:
        raw = node.payload.get("stop_contract")
    if raw is None:
        return None
    if isinstance(raw, StopContract):
        return raw
    if isinstance(raw, Mapping):
        return StopContract.model_validate(raw)
    return None


def node_is_repeating(node: GraphNode) -> bool:
    if getattr(node, "repeating", False):
        return True
    if node.payload.get("repeating") is True:
        return True
    return node.kind in {"loop", "repeat", "iterate"}


class DefaultLinkageResolver(LinkageResolver):
    """Standard preflight used by :class:`~mechaharness.graph_executor.GraphExecutor`."""

    def __init__(
        self,
        runners: RunnerRegistryLike,
        access: AccessControl,
        environment: InferenceEnvironment,
        *,
        operations: OperationRegistry | None = None,
        require_execute_grant: bool = True,
    ) -> None:
        self.runners = runners
        self.access = access
        self.environment = environment
        self.operations = operations
        self.require_execute_grant = require_execute_grant

    def resolve(
        self,
        graph: ExecutionGraph,
        *,
        envelope: CapabilityEnvelope | None = None,
        fingerprint_parts: Mapping[str, Any] | None = None,
    ) -> LinkageReport:
        edges: list[UnsatisfiedEdge] = []
        if self.require_execute_grant and not self.access.allows([GraphExecute]):
            edges.append(
                UnsatisfiedEdge(
                    code="missing_grant",
                    message="core:graph.execute required to run graphs",
                    candidate_provider="AccessControl / Config.get_grants",
                )
            )

        if not graph.nodes:
            # Empty graphs are allowed (no work); still fingerprint.
            pass

        for node in graph.nodes.values():
            edges.extend(self._check_node(node, envelope=envelope))

        # Termination: at least one node without dependents or all succeed paths.
        if graph.nodes and not self._has_termination_path(graph):
            edges.append(
                UnsatisfiedEdge(
                    code="no_termination_path",
                    message="graph has no sink node / termination path",
                    candidate_provider="add a terminal node or edge",
                )
            )

        try:
            self.environment.assert_compatible(
                required_grants=list(envelope.grants) if envelope else None,
            )
        except Exception as exc:  # noqa: BLE001 - surface as linkage edge
            edges.append(
                UnsatisfiedEdge(
                    code="environment_incompatible",
                    message=str(exc),
                    candidate_provider="InferenceEnvironment / host profile",
                )
            )

        parts = {
            "graph_version": graph.version,
            "graph_id": graph.id,
            "node_kinds": sorted({n.kind for n in graph.nodes.values()}),
            "runner_kinds": self.runners.kinds(),
            **dict(fingerprint_parts or {}),
        }
        fingerprint = _fingerprint(parts)
        return LinkageReport(ok=not edges, edges=edges, fingerprint=fingerprint)

    def _check_node(
        self,
        node: GraphNode,
        *,
        envelope: CapabilityEnvelope | None,
    ) -> list[UnsatisfiedEdge]:
        found: list[UnsatisfiedEdge] = []
        if node.kind == "subgraph" or node.subgraph:
            # Nested graphs are executed by GraphExecutor; child kinds resolve separately.
            return found
        runner = self.runners.get(node.kind)
        if runner is None:
            found.append(
                UnsatisfiedEdge(
                    code="no_runner",
                    message=f"no runner registered for kind {node.kind!r}",
                    node_id=node.id,
                    kind=node.kind,
                    candidate_provider="GraphNodeRunnerRegistry / Config.get_node_runner_registry",
                )
            )
        else:
            required_grants: Sequence[object] = ()
            if hasattr(runner, "required_grants"):
                required_grants = tuple(runner.required_grants())
            for grant in required_grants:
                key = grant_key(grant)
                if not self.access.allows([grant]):
                    found.append(
                        UnsatisfiedEdge(
                            code="missing_grant",
                            message=f"runner requires {key}",
                            node_id=node.id,
                            kind=node.kind,
                            candidate_provider="AccessControl / Config.get_grants",
                            detail={"grant": key},
                        )
                    )
                if envelope is not None and envelope.grants and key not in envelope.grants:
                    found.append(
                        UnsatisfiedEdge(
                            code="envelope_grant",
                            message=f"envelope lacks grant {key}",
                            node_id=node.id,
                            kind=node.kind,
                            candidate_provider="CapabilityEnvelope",
                            detail={"grant": key},
                        )
                    )

        if node_is_repeating(node):
            stop = stop_contract_from_node(node)
            if stop is None:
                found.append(
                    UnsatisfiedEdge(
                        code="missing_stop_contract",
                        message="repeating node requires a stop_contract",
                        node_id=node.id,
                        kind=node.kind,
                        candidate_provider="StopContract on node.payload['stop_contract']",
                    )
                )
            elif stop.is_bounded() and stop.max_iterations < 1:
                found.append(
                    UnsatisfiedEdge(
                        code="unbounded_stop",
                        message="bounded stop_contract needs max_iterations >= 1",
                        node_id=node.id,
                        kind=node.kind,
                        candidate_provider="StopContract",
                    )
                )

        op_name = node.payload.get("operation") or getattr(node, "operation", None)
        if op_name and self.operations is not None:
            try:
                self.operations.contract(str(op_name))
            except Exception as exc:  # noqa: BLE001
                found.append(
                    UnsatisfiedEdge(
                        code="operation_unbound",
                        message=str(exc),
                        node_id=node.id,
                        kind=node.kind,
                        candidate_provider="OperationRegistry",
                        detail={"operation": str(op_name)},
                    )
                )

        needs = node.payload.get("capability_needs") or []
        if envelope is not None and needs:
            model_class = envelope.model_class
            for need in needs:
                if isinstance(need, str) and need.startswith("model:") and model_class:
                    required = need.split(":", 1)[1]
                    if required != model_class:
                        found.append(
                            UnsatisfiedEdge(
                                code="model_class_mismatch",
                                message=f"node needs model:{required}, envelope has {model_class}",
                                node_id=node.id,
                                kind=node.kind,
                                candidate_provider="CapabilityEnvelope.model_class",
                            )
                        )
        return found

    def _has_termination_path(self, graph: ExecutionGraph) -> bool:
        # A sink is a node that no other node lists as a dependency.
        prerequisites: set[str] = set()
        for node in graph.nodes.values():
            prerequisites.update(node.depends_on)
        for edge in graph.edges:
            prerequisites.add(edge.from_node)
        sinks = [nid for nid in graph.nodes if nid not in prerequisites]
        return bool(sinks) or len(graph.nodes) <= 1


def _fingerprint(parts: Mapping[str, Any]) -> str:
    import hashlib
    import json

    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class NoOpLinkageResolver(LinkageResolver):
    """Skip validation (tests / hosts that resolve externally)."""

    def resolve(
        self,
        graph: ExecutionGraph,
        *,
        envelope: CapabilityEnvelope | None = None,
        fingerprint_parts: Mapping[str, Any] | None = None,
    ) -> LinkageReport:
        del envelope
        parts = {
            "graph_version": graph.version,
            "graph_id": graph.id,
            **dict(fingerprint_parts or {}),
        }
        return LinkageReport(ok=True, fingerprint=_fingerprint(parts))
