"""Reusable parameterized graph templates (library-owned subgraph skeletons).

A template is intentionally incomplete: it exposes soft points for client
bindings (tools, providers, prompts, models, budgets, persistence, policies).
Clients instantiate, bind, and may retain the resulting concrete
:class:`~mechaharness.graph.ExecutionGraph` in their own repository.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.stop_contract import StopContract

SoftPointKind = Literal[
    "tool",
    "provider",
    "prompt",
    "model",
    "budget",
    "persistence",
    "policy",
    "task_state",
    "runner_kind",
    "other",
]
TemplateStatus = Literal["active", "deprecated", "demoted"]


class SoftPoint(BaseModel):
    """Declared client-binding slot on a reusable template."""

    model_config = ConfigDict(extra="allow")

    name: str
    kind: SoftPointKind = "other"
    description: str = ""
    required: bool = False
    default: Any = None


class GraphTemplateParams(BaseModel):
    """Client bindings applied when instantiating a template."""

    model_config = ConfigDict(extra="allow")

    goal: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    branch_payloads: list[dict[str, Any]] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    stop_contract: StopContract | None = None
    envelope_ref: str | None = None
    soft_bindings: dict[str, Any] = Field(default_factory=dict)
    source_workflow_ref: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class GraphTemplate(ABC):
    """Reusable parameterized subgraph factory."""

    name: str = "template"
    version: str = "1"
    summary: str = ""
    status: TemplateStatus = "active"
    soft_points: tuple[SoftPoint, ...] = ()

    @abstractmethod
    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        """Construct the skeleton graph (subclasses implement this)."""

    def instantiate(self, params: GraphTemplateParams) -> ExecutionGraph:
        """Build a concrete graph and stamp template provenance."""
        if self.status == "demoted":
            raise RuntimeError(
                f"template {self.name!r} is demoted; move bindings to the client"
            )
        graph = self.build(params)
        return self.stamp(graph, params=params)

    def stamp(
        self, graph: ExecutionGraph, *, params: GraphTemplateParams | None = None
    ) -> ExecutionGraph:
        """Attach template identity for promotion / deprecation detection."""
        graph.template_name = self.name
        graph.template_version = self.version
        graph.template_status = self.status
        if params is not None and params.source_workflow_ref:
            graph.source_workflow_ref = params.source_workflow_ref
        return graph

    def describe(self) -> dict[str, Any]:
        """Stable metadata for docs, catalogs, and promotion provenance."""
        return {
            "name": self.name,
            "version": self.version,
            "summary": self.summary,
            "status": self.status,
            "soft_points": [p.model_dump(mode="json") for p in self.soft_points],
        }


class GraphTemplateRegistry:
    """Library + host-merged template map (Config hook)."""

    def __init__(self, templates: Sequence[GraphTemplate] | None = None) -> None:
        self._by_name: dict[str, GraphTemplate] = {}
        for template in templates or []:
            self.register(template)

    def register(self, template: GraphTemplate) -> None:
        self._by_name[template.name] = template

    def get(self, name: str) -> GraphTemplate | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return sorted(self._by_name)

    def active_names(self) -> list[str]:
        return sorted(
            n for n, t in self._by_name.items() if t.status == "active"
        )

    def merge(self, other: GraphTemplateRegistry) -> GraphTemplateRegistry:
        for name in other.names():
            template = other.get(name)
            if template is not None:
                self.register(template)
        return self

    def catalog(self) -> list[dict[str, Any]]:
        return [self._by_name[n].describe() for n in self.names()]


def make_node(
    *,
    id: str | None = None,
    kind: str,
    goal: str = "",
    depends_on: Sequence[str] | None = None,
    payload: Mapping[str, Any] | None = None,
    write_scopes: Sequence[str] | None = None,
    repeating: bool = False,
    stop_contract: StopContract | None = None,
    acceptance: Sequence[str] | None = None,
) -> GraphNode:
    """Build a :class:`~mechaharness.graph.GraphNode` for template skeletons."""
    return GraphNode(
        id=id or str(uuid4()),
        kind=kind,
        goal=goal,
        depends_on=list(depends_on or []),
        payload=dict(payload or {}),
        write_scopes=list(write_scopes or []),
        repeating=repeating,
        stop_contract=stop_contract.model_dump(mode="json") if stop_contract else None,
        acceptance=list(acceptance or []),
    )


class SubgraphNodeRunner:
    """Marker helpers for nesting child graphs under a parent node."""

    KIND = "subgraph"

    @staticmethod
    def embed(child: ExecutionGraph, *, parent_node_id: str) -> GraphNode:
        return GraphNode(
            id=parent_node_id,
            kind=SubgraphNodeRunner.KIND,
            goal=child.goal,
            subgraph=child.checkpoint(),
            payload={"child_graph_id": child.id, "child_version": child.version},
        )
