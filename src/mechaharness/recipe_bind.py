"""Human-readable recipe bind documents for stories and the CLI.

A :class:`RecipeBind` is the serialized parameterization of an Agentic Recipe.
Authors write the **decisions that matter** (goal, acceptance, soft bindings
they care about). Omitted soft points take the template default. Unknown soft
point keys always fail. The same YAML shape loads from story ``binds/`` files
or from a CLI ``path=``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.graph import ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    GraphTemplateRegistry,
)
from mechaharness.stop_contract import StopContract


def _stop_max_iterations(stop: Any) -> int | None:
    if stop is None:
        return None
    if isinstance(stop, Mapping):
        value = stop.get("max_iterations")
        return int(value) if value is not None else None
    value = getattr(stop, "max_iterations", None)
    return int(value) if value is not None else None


class RecipeBind(BaseModel):
    """Bind parameters for instantiating one catalog recipe.

    Field order is documentation order: who / what / acceptance / inputs /
    soft decisions. ``summary`` is prose for readers; it does not affect
    instantiation.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    summary: str = ""
    goal: str = ""
    version: str | None = None
    acceptance: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    soft_bindings: dict[str, Any] = Field(default_factory=dict)
    stop_contract: StopContract | None = None
    branch_payloads: list[dict[str, Any]] = Field(default_factory=list)
    source_workflow_ref: str | None = None
    instance_key: str | None = None
    envelope_ref: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> RecipeBind:
        return cls.model_validate(dict(data))

    @classmethod
    def from_path(cls, path: str | Path) -> RecipeBind:
        file_path = Path(path)
        raw = file_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: recipe bind root must be a mapping")
        return cls.from_mapping(data)

    def materialize(self, template: GraphTemplate) -> RecipeBind:
        """Fill omitted soft points from template defaults; reject unknown keys."""
        declared = {point.name: point for point in template.soft_points}
        unknown = sorted(set(self.soft_bindings) - set(declared))
        if unknown:
            raise ValueError(
                f"recipe bind {self.name!r} unknown soft points: {unknown}"
            )
        merged: dict[str, Any] = {}
        missing_required: list[str] = []
        for name, point in declared.items():
            if name in self.soft_bindings:
                merged[name] = self.soft_bindings[name]
                continue
            if point.default is not None:
                merged[name] = point.default
                continue
            if point.required:
                missing_required.append(name)
        if missing_required:
            raise ValueError(
                f"recipe bind {self.name!r} missing required soft points: "
                f"{missing_required}"
            )
        if self.version is not None and self.version != template.version:
            raise ValueError(
                f"recipe bind {self.name!r} version pin {self.version!r} "
                f"!= template {template.version!r}"
            )
        return self.model_copy(update={"soft_bindings": merged})

    def to_params(self) -> GraphTemplateParams:
        """Map this document onto :class:`GraphTemplateParams`."""
        stop = self.stop_contract
        raw_stop = self.soft_bindings.get("stop_contract")
        if stop is None and isinstance(raw_stop, dict):
            stop = StopContract.model_validate(raw_stop)
        elif stop is None and isinstance(raw_stop, StopContract):
            stop = raw_stop
        return GraphTemplateParams(
            goal=self.goal,
            inputs=dict(self.inputs),
            acceptance=list(self.acceptance),
            soft_bindings=dict(self.soft_bindings),
            stop_contract=stop,
            branch_payloads=list(self.branch_payloads),
            source_workflow_ref=self.source_workflow_ref,
            instance_key=self.instance_key,
            envelope_ref=self.envelope_ref,
        )

    def resolve_template(
        self,
        registry: GraphTemplateRegistry | None = None,
    ) -> tuple[GraphTemplate, RecipeBind]:
        from mechaharness.recipe_runner import get_recipe

        template = get_recipe(self.name, registry=registry)
        return template, self.materialize(template)

    def instantiate(
        self,
        registry: GraphTemplateRegistry | None = None,
    ) -> ExecutionGraph:
        """Materialize defaults and expand into an :class:`ExecutionGraph`."""
        from mechaharness.recipe_runner import instantiate_recipe

        _template, bound = self.resolve_template(registry=registry)
        return instantiate_recipe(bound.name, bound.to_params(), registry=registry)


class InstantiateRecipeCommand(BaseModel):
    """CLI verb body: inline :class:`RecipeBind` fields or ``path`` to a bind file."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    name: str | None = None
    summary: str = ""
    goal: str = ""
    version: str | None = None
    acceptance: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    soft_bindings: dict[str, Any] = Field(default_factory=dict)
    stop_contract: StopContract | None = None
    branch_payloads: list[dict[str, Any]] = Field(default_factory=list)
    source_workflow_ref: str | None = None
    instance_key: str | None = None
    envelope_ref: str | None = None

    @model_validator(mode="after")
    def _path_or_inline(self) -> InstantiateRecipeCommand:
        if self.path:
            return self
        if not self.name:
            raise ValueError("instantiate_recipe requires name= or path=")
        return self

    def resolve_bind(self, *, base_dir: Path | None = None) -> RecipeBind:
        if self.path:
            file_path = Path(self.path)
            if not file_path.is_absolute():
                root = base_dir if base_dir is not None else Path.cwd()
                file_path = (root / file_path).resolve()
            return RecipeBind.from_path(file_path)
        assert self.name is not None
        return RecipeBind(
            name=self.name,
            summary=self.summary,
            goal=self.goal,
            version=self.version,
            acceptance=list(self.acceptance),
            inputs=dict(self.inputs),
            soft_bindings=dict(self.soft_bindings),
            stop_contract=self.stop_contract,
            branch_payloads=list(self.branch_payloads),
            source_workflow_ref=self.source_workflow_ref,
            instance_key=self.instance_key,
            envelope_ref=self.envelope_ref,
        )


def observe_instantiated_recipe(
    bind: RecipeBind,
    graph: ExecutionGraph,
    template: GraphTemplate,
) -> dict[str, Any]:
    """Structural observation for instantiate_recipe (stories + CLI)."""
    from mechaharness.node_component import NODE_COMPONENT_KINDS, node_components_for
    from mechaharness.recipe_runner import list_recipes

    catalog_rows = list_recipes()
    catalog = {row["name"] for row in catalog_rows}
    in_catalog = bind.name in catalog
    comps = node_components_for(graph, template=template)
    parents: dict[str, list[str]] = {}
    for comp in comps:
        parents.setdefault(comp.parent_node_id, []).append(
            comp.soft_point_name or comp.kind
        )
    kinds = {c.kind for c in comps}
    fields: dict[str, Any] = {
        "template_name": graph.template_name,
        "template_status": graph.template_status,
        "source_workflow_ref": graph.source_workflow_ref,
        "recipe_category": getattr(template, "category", None),
        "evolvable": list(template.evolvable_soft_point_names()),
        "component_parents": {k: sorted(v) for k, v in sorted(parents.items())},
        "in_default_catalog": in_catalog,
        "catalog_soft_points_nonempty": all(
            bool(row.get("soft_points")) for row in catalog_rows
        ),
        "all_have_parent": all(bool(c.parent_node_id) for c in comps),
        "kinds_subset_catalog": kinds <= NODE_COMPONENT_KINDS,
        "has_stop_contract": "stop_contract" in kinds,
        "has_soft_point": "soft_point" in kinds,
        "summary": bind.summary,
        "soft_bindings": dict(bind.soft_bindings),
    }
    name = bind.name
    if name == "independent_review":
        reviews = [n for n in graph.nodes if n.startswith("review_")]
        fields["review_count"] = len(reviews)
        if reviews:
            fields["omit_producer_reasoning"] = bool(
                graph.nodes[reviews[0]].payload.get("omit_producer_reasoning")
            )
        fields["retain_disagreement"] = bool(
            graph.nodes["aggregate_reviews"].payload.get("retain_disagreement")
        )
    elif name == "bounded_retry":
        attempt = graph.nodes["attempt"]
        fields["attempt_repeating"] = bool(attempt.repeating)
        fields["max_iterations"] = _stop_max_iterations(attempt.stop_contract)
        fields["requires_effect_reconciliation"] = bool(
            attempt.payload.get("requires_effect_reconciliation")
        )
    elif name == "produce_critique_refine":
        critique = graph.nodes["critique"].payload
        fields["critic_isolated"] = bool(
            critique.get("isolated_context") and critique.get("omit_producer_reasoning")
        )
        fields["refine_max_iterations"] = _stop_max_iterations(
            graph.nodes["refine"].stop_contract
        )
    elif name == "safety_eval":
        review = graph.nodes["review"].payload
        score = graph.nodes["score"].payload
        fields["reviewer_isolated"] = bool(
            review.get("isolated_context") and review.get("omit_producer_reasoning")
        )
        fields["score_deterministic"] = bool(score.get("deterministic"))
        fields["report_fields"] = list(score.get("report_fields") or [])
        fields["reported_versions"] = [
            score.get("model_version"),
            score.get("recipe_version"),
        ]
        fields["scenario_classes"] = list(
            graph.nodes["produce"].payload.get("scenario_classes") or []
        )
    return {
        "recipe_in_catalog": in_catalog,
        "subgraph_node_ids": list(graph.nodes),
        "fields": fields,
    }


class RecipeTileBind(BaseModel):
    """Tile one catalog recipe under multiple instance keys (readable composition)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    summary: str = ""
    instance_keys: list[str] = Field(min_length=1)
    soft_bindings: dict[str, Any] = Field(default_factory=dict)
    acceptance: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> RecipeTileBind:
        return cls.model_validate(dict(data))

    @classmethod
    def from_path(cls, path: str | Path) -> RecipeTileBind:
        file_path = Path(path)
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path}: recipe tile bind root must be a mapping")
        return cls.from_mapping(data)

    def tile(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        """Expand each instance key and return structural observation fields."""
        from mechaharness.graph import ExecutionGraph
        from mechaharness.recipe_runner import get_recipe

        template = get_recipe(self.name, registry=registry)
        # Reuse RecipeBind materialize rules for shared soft bindings.
        seed = RecipeBind(
            name=self.name,
            soft_bindings=dict(self.soft_bindings),
            acceptance=list(self.acceptance),
            inputs=dict(self.inputs),
        ).materialize(template)
        parent = ExecutionGraph(goal="parent")
        children = []
        embeds = []
        for key in self.instance_keys:
            child, embed = template.tile(
                GraphTemplateParams(
                    goal=f"{self.name}:{key}",
                    instance_key=str(key),
                    soft_bindings=dict(seed.soft_bindings),
                    acceptance=list(seed.acceptance),
                    inputs=dict(seed.inputs),
                ),
                parent_node_id=f"embed_{key}",
            )
            children.append(child)
            embeds.append(embed)
            parent.add_node(embed)
        id_sets = [set(c.nodes) for c in children]
        overlap = (
            bool(id_sets[0].intersection(*id_sets[1:])) if len(id_sets) > 1 else False
        )
        prefix_left = f"{self.name}/{self.instance_keys[0]}/"
        return {
            "summary": self.summary,
            "template_name": self.name,
            "instance_count": len(children),
            "node_id_overlap": overlap,
            "distinct_instance_ids": len({c.recipe_instance_id for c in children})
            == len(children),
            "parent_embed_kinds": [e.kind for e in embeds],
            "namespaced_prefix_left": prefix_left,
        }


class TileRecipeCommand(BaseModel):
    """CLI verb body: inline :class:`RecipeTileBind` or ``path`` to a tile file."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    name: str | None = None
    summary: str = ""
    instance_keys: list[str] = Field(default_factory=list)
    soft_bindings: dict[str, Any] = Field(default_factory=dict)
    acceptance: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _path_or_inline(self) -> TileRecipeCommand:
        if self.path:
            return self
        if not self.name or not self.instance_keys:
            raise ValueError("tile_recipe requires path= or name= with instance_keys=")
        return self

    def resolve_bind(self, *, base_dir: Path | None = None) -> RecipeTileBind:
        if self.path:
            file_path = Path(self.path)
            if not file_path.is_absolute():
                root = base_dir if base_dir is not None else Path.cwd()
                file_path = (root / file_path).resolve()
            return RecipeTileBind.from_path(file_path)
        assert self.name is not None
        return RecipeTileBind(
            name=self.name,
            summary=self.summary,
            instance_keys=list(self.instance_keys),
            soft_bindings=dict(self.soft_bindings),
            acceptance=list(self.acceptance),
            inputs=dict(self.inputs),
        )


__all__ = [
    "InstantiateRecipeCommand",
    "RecipeBind",
    "RecipeTileBind",
    "TileRecipeCommand",
    "observe_instantiated_recipe",
]
