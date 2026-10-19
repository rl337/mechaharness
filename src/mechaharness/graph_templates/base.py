"""Reusable parameterized graph templates (Agentic Recipe substrate).

A template is intentionally incomplete: it exposes soft points for client
bindings (tools, providers, prompts, models, budgets, persistence, policies).
Concrete, useful templates are documented as **Agentic Recipes**. Clients
instantiate, bind, and may retain the resulting concrete
:class:`~mechaharness.graph.ExecutionGraph` in their own repository.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence  # Mapping used by registry ctor
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.evaluator import EvaluatorResult, require_held_out_final_test
from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.isolation.isolation_contract import TemplateIOContract
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
    # Only soft points marked evolvable may be rewritten by an optimizer
    # (MH-SR-03); everything else is hard-immutable structure.
    evolvable: bool = False


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
    # Optional typed ports; ``recipe_port_search`` matches on these (MH-SR-04).
    io_contract: TemplateIOContract | None = None

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

    def documentation(self) -> str:
        """Full pydoc for CLI ``recipes show`` (module + class, with examples).

        Emits the defining module docstring (what / when) then the concrete
        class docstring (including ``Example:`` blocks). Falls back to
        :attr:`summary` when neither exists.
        """
        cls = type(self)
        parts: list[str] = []
        module = inspect.getmodule(cls)
        if module is not None and module.__doc__:
            module_doc = inspect.cleandoc(module.__doc__).strip()
            if module_doc:
                parts.append(module_doc)
        class_doc = (inspect.getdoc(cls) or "").strip()
        if class_doc and class_doc not in parts:
            parts.append(class_doc)
        if not parts:
            return str(self.summary or self.name)
        return "\n\n".join(parts)

    def evolvable_soft_point_names(self) -> list[str]:
        """Soft points an optimizer may rewrite (the declared evolution allowlist)."""
        return [p.name for p in self.soft_points if p.evolvable]

    def assert_evolution_allowed(self, changed: Sequence[str]) -> None:
        """Refuse optimizer edits outside the evolvable soft-point allowlist."""
        allowed = set(self.evolvable_soft_point_names())
        blocked = sorted(set(changed) - allowed)
        if blocked:
            raise ValueError(
                f"recipe {self.name!r} forbids evolving non-evolvable fields: {blocked}"
            )

    def describe(self) -> dict[str, Any]:
        """Stable metadata for docs, catalogs, and promotion provenance."""
        return {
            "name": self.name,
            "version": self.version,
            "summary": self.summary,
            "status": self.status,
            "category": self.category,
            "doc": self.documentation(),
            "soft_points": [p.model_dump(mode="json") for p in self.soft_points],
        }


class GraphTemplateRegistry:
    """Library + host-merged template map (DI map-multibind facade).

    Prefer contributing classes via
    :meth:`MechaHarnessConfig.graph_template_classes` /
    ``contribute_map(GraphTemplate, …)``. When constructed by pyiv, ``templates``
    is the injected ``Dict[str, GraphTemplate]`` catalog. Hand construction may
    still pass a sequence of instances (tests / ``default_graph_templates``).

    Entries are versioned: :meth:`register` activates the template (legacy
    replace-by-name behavior); :meth:`add_version` stores an immutable
    candidate without activating it. :meth:`promote` moves the active pointer
    and :meth:`rollback` returns it to the previous target::

        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateRegistry, VerifyRepairTemplate,
        ... )
        >>> class VerifyRepairV2(VerifyRepairTemplate):
        ...     version = "2"
        >>> registry = GraphTemplateRegistry([VerifyRepairTemplate()])
        >>> registry.add_version(VerifyRepairV2())
        >>> registry.get("verify_repair").version
        '1'
        >>> registry.promote("verify_repair", "2")
        >>> registry.get("verify_repair").version
        '2'
        >>> registry.rollback("verify_repair")
        '1'
        >>> registry.versions("verify_repair")
        ['1', '2']

    Lineage and evaluation results ride on immutable versions::

        >>> registry.lineage("verify_repair")
        {'1': None, '2': None}
        >>> registry.attach_evaluation("verify_repair", "2", {"pass_rate": 0.9})
        >>> registry.evaluations("verify_repair", "2")
        [{'pass_rate': 0.9}]
    """

    def __init__(self, templates: dict[str, GraphTemplate]) -> None:
        # Annotation is dict[str, GraphTemplate] so pyiv injects the map multibind.
        # Callers may still pass a sequence of instances (runtime Sequence path).
        self._versions: dict[str, dict[str, GraphTemplate]] = {}
        self._active: dict[str, str] = {}
        self._pointer_history: dict[str, list[str]] = {}
        self._lineage: dict[str, dict[str, str | None]] = {}
        self._evaluations: dict[str, dict[str, list[dict[str, Any]]]] = {}
        if isinstance(templates, Mapping):
            for name, template in templates.items():
                self._store(str(name), template, activate=True)
            return
        for template in cast(Sequence[GraphTemplate], templates):
            self.register(template)

    def _store(
        self,
        name: str,
        template: GraphTemplate,
        *,
        activate: bool,
        parent_version: str | None = None,
    ) -> None:
        self._versions.setdefault(name, {})[template.version] = template
        self._lineage.setdefault(name, {}).setdefault(template.version, parent_version)
        if activate or name not in self._active:
            self._set_active(name, template.version)

    def _set_active(self, name: str, version: str) -> None:
        current = self._active.get(name)
        if current is not None and current != version:
            self._pointer_history.setdefault(name, []).append(current)
        self._active[name] = version

    def register(self, template: GraphTemplate) -> None:
        """Register and activate ``template`` (replaces the same name+version)."""
        self._store(template.name, template, activate=True)

    def add_version(
        self, template: GraphTemplate, *, parent_version: str | None = None
    ) -> None:
        """Add an immutable candidate version; it does not become active.

        ``parent_version`` records lineage (which stored version this one was
        derived from).
        """
        existing = self._versions.get(template.name, {}).get(template.version)
        if existing is not None and existing is not template:
            raise ValueError(
                f"recipe {template.name!r} version {template.version!r} is immutable"
            )
        if parent_version is not None and parent_version not in self._versions.get(
            template.name, {}
        ):
            raise KeyError(f"unknown parent version {template.name}@{parent_version}")
        self._store(
            template.name, template, activate=False, parent_version=parent_version
        )

    def lineage(self, name: str) -> dict[str, str | None]:
        """Version → parent version (``None`` for roots): the recipe lineage DAG."""
        return dict(self._lineage.get(name, {}))

    def attach_evaluation(
        self, name: str, version: str, result: Mapping[str, Any]
    ) -> None:
        """Attach an evaluation result to an immutable stored version."""
        if version not in self._versions.get(name, {}):
            raise KeyError(f"unknown recipe version {name}@{version}")
        self._evaluations.setdefault(name, {}).setdefault(version, []).append(
            dict(result)
        )

    def evaluations(self, name: str, version: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._evaluations.get(name, {}).get(version, [])]

    def composition_violations(self, graph: ExecutionGraph) -> list[str]:
        """List reasons ``graph`` is not composed only from registered recipes.

        A graph stamped by a recipe must name a stored ``name@version``. An
        unstamped graph is a pure tiling container: every node must embed a
        child graph, which is checked recursively. Free-form nodes are
        violations (MH-SR-02).
        """
        issues: list[str] = []
        if graph.template_name is not None:
            if self.get(graph.template_name, graph.template_version) is None:
                issues.append(
                    f"unregistered_recipe:{graph.template_name}@{graph.template_version}"
                )
        for node_id, node in graph.nodes.items():
            if node.subgraph:
                issues.extend(
                    self.composition_violations(ExecutionGraph.resume(node.subgraph))
                )
            elif graph.template_name is None:
                issues.append(f"free_form_node:{node_id}")
        return issues

    def assert_registry_composed(self, graph: ExecutionGraph) -> None:
        issues = self.composition_violations(graph)
        if issues:
            raise ValueError(f"graph is not registry-composed: {', '.join(issues)}")

    def versions(self, name: str) -> list[str]:
        return sorted(self._versions.get(name, {}))

    def active_version(self, name: str) -> str | None:
        return self._active.get(name)

    def promote(self, name: str, version: str) -> None:
        """Point ``name`` at an existing ``version`` (reversible via rollback)."""
        if version not in self._versions.get(name, {}):
            raise KeyError(f"unknown recipe version {name}@{version}")
        self._set_active(name, version)

    def promote_with_final_test(
        self, name: str, version: str, *, final_test: EvaluatorResult | None
    ) -> None:
        """Promote only after a passing held-out final-test result (MH-SR-07).

        The result is attached as an evaluation of ``name@version`` once the gate
        opens. Plain :meth:`promote` stays a pointer move for hosts that run
        their own gate.
        """
        if version not in self._versions.get(name, {}):
            raise KeyError(f"unknown recipe version {name}@{version}")
        require_held_out_final_test(final_test)
        if final_test is not None:  # always true once the gate has passed
            self.attach_evaluation(
                name,
                version,
                {"gate": "final_test", **final_test.model_dump(mode="json")},
            )
        self._set_active(name, version)

    def search_compatible(
        self,
        required_inputs: Mapping[str, Any] | None = None,
        required_outputs: Mapping[str, Any] | None = None,
    ) -> list[str]:
        """Catalog ids of active recipes whose typed ports fit the request (MH-SR-04).

        Delegates to ``recipe_lifecycle.recipe_port_search.search_compatible_recipes``.
        """
        # Lazy: port search imports this module's registry type.
        from mechaharness.recipe_lifecycle.recipe_port_search import (
            search_compatible_recipes,
        )

        return search_compatible_recipes(self, required_inputs, required_outputs)

    def rollback(self, name: str) -> str:
        """Restore the previously active version; return it."""
        history = self._pointer_history.get(name) or []
        if not history:
            raise ValueError(f"recipe {name!r} has no previous version to roll back to")
        previous = history.pop()
        self._active[name] = previous
        return previous

    def get(self, name: str, version: str | None = None) -> GraphTemplate | None:
        """Return the active template, or a specific ``version`` when given."""
        by_version = self._versions.get(name)
        if not by_version:
            return None
        if version is not None:
            return by_version.get(version)
        return by_version.get(self._active[name])

    def names(self) -> list[str]:
        return sorted(self._versions)

    def active_names(self) -> list[str]:
        return sorted(
            n for n in self._versions if (t := self.get(n)) is not None and t.status == "active"
        )

    def merge(self, other: GraphTemplateRegistry) -> GraphTemplateRegistry:
        for name in other.names():
            for version in other.versions(name):
                template = other.get(name, version)
                if template is not None:
                    self._store(
                        name,
                        template,
                        activate=False,
                        parent_version=other.lineage(name).get(version),
                    )
                    for result in other.evaluations(name, version):
                        self.attach_evaluation(name, version, result)
            active = other.active_version(name)
            if active is not None:
                self._set_active(name, active)
        return self

    def catalog(self) -> list[dict[str, Any]]:
        return [
            t.describe() for n in self.names() if (t := self.get(n)) is not None
        ]


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
