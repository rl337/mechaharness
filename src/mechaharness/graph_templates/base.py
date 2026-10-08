"""Reusable parameterized graph templates (Agentic Recipe substrate).

A template is intentionally incomplete: it exposes soft points for client
bindings (tools, providers, prompts, models, budgets, persistence, policies).
Concrete, useful templates are documented as **Agentic Recipes**. Clients
instantiate, bind, and may retain the resulting concrete
:class:`~mechaharness.graph.ExecutionGraph` in their own repository.
"""

from __future__ import annotations

import hashlib
import json
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
TemplateCategory = Literal["agentic_recipe", "skeleton"]


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
    instance_key: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class GraphTemplate(ABC):
    """Reusable parameterized subgraph factory (Agentic Recipe substrate)."""

    name: str = "template"
    version: str = "1"
    summary: str = ""
    status: TemplateStatus = "active"
    category: TemplateCategory = "agentic_recipe"
    soft_points: tuple[SoftPoint, ...] = ()

    @abstractmethod
    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        """Construct the skeleton graph (subclasses implement this)."""

    def instantiate(self, params: GraphTemplateParams) -> ExecutionGraph:
        """Build a concrete graph, namespace if needed, and stamp provenance."""
        if self.status == "demoted":
            raise RuntimeError(
                f"template {self.name!r} is demoted; move bindings to the client"
            )
        self.validate_soft_bindings(params)
        graph = self.build(params)
        logical_ids = list(graph.nodes)
        if params.instance_key:
            graph = namespace_graph(graph, prefix=f"{self.name}/{params.instance_key}")
        return self.stamp(graph, params=params, logical_ids=logical_ids)

    def tile(
        self,
        params: GraphTemplateParams,
        *,
        parent_node_id: str,
    ) -> tuple[ExecutionGraph, GraphNode]:
        """Instantiate and embed under ``parent_node_id`` (readable composition)."""
        child = self.instantiate(params)
        embed = SubgraphNodeRunner.embed(child, parent_node_id=parent_node_id)
        return child, embed

    def validate_soft_bindings(self, params: GraphTemplateParams) -> None:
        """Fail early when required soft points lack binding and default."""
        missing: list[str] = []
        for point in self.soft_points:
            if not point.required:
                continue
            if point.name in params.soft_bindings:
                continue
            if point.default is not None:
                continue
            missing.append(point.name)
        if missing:
            raise ValueError(
                f"recipe {self.name!r} missing required soft points: {missing}"
            )

    def stamp(
        self,
        graph: ExecutionGraph,
        *,
        params: GraphTemplateParams | None = None,
        logical_ids: Sequence[str] | None = None,
    ) -> ExecutionGraph:
        """Attach template / recipe identity for provenance and deprecation."""
        graph.template_name = self.name
        graph.template_version = self.version
        graph.template_status = self.status
        graph.recipe_definition_fingerprint = definition_fingerprint(
            name=self.name, version=self.version, summary=self.summary
        )
        if params is not None:
            if params.source_workflow_ref:
                graph.source_workflow_ref = params.source_workflow_ref
            graph.recipe_instance_id = (
                f"{self.name}/{params.instance_key}"
                if params.instance_key
                else f"{self.name}#{graph.recipe_definition_fingerprint[:8]}"
            )
            graph.recipe_params_fingerprint = params_fingerprint(params)
            if logical_ids is not None:
                if params.instance_key:
                    prefix = f"{self.name}/{params.instance_key}/"
                    graph.recipe_node_map = {
                        logical: f"{prefix}{logical}" for logical in logical_ids
                    }
                else:
                    graph.recipe_node_map = {logical: logical for logical in logical_ids}
        return graph

    def describe(self) -> dict[str, Any]:
        """Stable metadata for docs, catalogs, and promotion provenance."""
        return {
            "name": self.name,
            "version": self.version,
            "summary": self.summary,
            "status": self.status,
            "category": self.category,
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


def namespace_graph(graph: ExecutionGraph, *, prefix: str) -> ExecutionGraph:
    """Rewrite node ids / edges under ``prefix/`` (deterministic, no inference)."""
    bare = prefix.rstrip("/")
    mapping = {old: f"{bare}/{old}" for old in graph.nodes}
    remapped = ExecutionGraph(
        id=graph.id,
        goal=graph.goal,
        version=graph.version,
        config_fingerprint=graph.config_fingerprint,
        template_name=graph.template_name,
        template_version=graph.template_version,
        template_status=graph.template_status,
        source_workflow_ref=graph.source_workflow_ref,
    )
    for old_id, node in graph.nodes.items():
        new = node.model_copy(deep=True)
        new.id = mapping[old_id]
        new.depends_on = [mapping.get(d, d) for d in node.depends_on]
        remapped.add_node(new)
    for edge in graph.edges:
        remapped.add_dependency(
            edge.model_copy(
                update={
                    "from_node": mapping.get(edge.from_node, edge.from_node),
                    "to_node": mapping.get(edge.to_node, edge.to_node),
                }
            )
        )
    return remapped


def definition_fingerprint(*, name: str, version: str, summary: str) -> str:
    payload = json.dumps(
        {"name": name, "version": version, "summary": summary},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def params_fingerprint(params: GraphTemplateParams) -> str:
    payload = json.dumps(params.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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
            payload={
                "child_graph_id": child.id,
                "child_version": child.version,
                "recipe_instance_id": child.recipe_instance_id,
                "template_name": child.template_name,
            },
        )
