"""Human-readable recipe lifecycle plans for stories and the CLI.

One verb (``recipe_plan``) loads a YAML document whose ``plan:`` field selects
the check. Authors put the scenarios that matter in prose-friendly files under
story ``plans/``; omitted details stay out of the way.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.graph_templates.base import GraphTemplateParams, GraphTemplateRegistry
from mechaharness.recipe_runner import resolve_registry

PlanKind = Literal["soft_evolution", "port_search", "registry_compose"]


class SoftEvolutionAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    recipe: str
    changed: list[str] = Field(min_length=1)


class SoftEvolutionPlan(BaseModel):
    """Which soft-point rewrites evolution may touch (MH-SR-03)."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["soft_evolution"] = "soft_evolution"
    summary: str = ""
    recipes: list[str] = Field(min_length=1)
    attempts: list[SoftEvolutionAttempt] = Field(min_length=1)

    def run(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        reg = resolve_registry(registry)
        outcomes: dict[str, str] = {}
        for attempt in self.attempts:
            template = reg.get(attempt.recipe)
            if template is None:
                raise KeyError(f"unknown recipe {attempt.recipe!r}")
            try:
                template.assert_evolution_allowed(attempt.changed)
                outcomes[attempt.id] = "allowed"
            except ValueError:
                outcomes[attempt.id] = "refused"
        evolvable = {
            name: list(reg.get(name).evolvable_soft_point_names())  # type: ignore[union-attr]
            for name in self.recipes
        }
        return {
            "summary": self.summary,
            "outcomes": outcomes,
            "evolvable": evolvable,
        }


class PortSearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    required_inputs: dict[str, Any] | None = None
    required_outputs: dict[str, Any] | None = None


class PortSearchPlan(BaseModel):
    """Typed-port catalog search (MH-SR-04)."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["port_search"] = "port_search"
    summary: str = ""
    queries: list[PortSearchQuery] = Field(min_length=1)

    def run(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        from mechaharness.recipe_lifecycle.recipe_port_search import (
            search_compatible_recipes,
        )

        reg = resolve_registry(registry)
        found = {
            q.id: search_compatible_recipes(
                reg, q.required_inputs, q.required_outputs
            )
            for q in self.queries
        }
        return {
            "summary": self.summary,
            "found": found,
            "all_catalog_ids": all(
                name in reg.names() for names in found.values() for name in names
            ),
            "undeclared_recipes_skipped": not any(
                reg.get(name).io_contract is None  # type: ignore[union-attr]
                for names in found.values()
                for name in names
            ),
        }


class RegistryComposeTile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe: str
    key: str
    forge_version: str | None = None


class RegistryComposeScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tiles: list[RegistryComposeTile] = Field(default_factory=list)
    free_form_nodes: list[str] = Field(default_factory=list)


class RegistryComposePlan(BaseModel):
    """Production graphs may only compose registered recipes (MH-SR-02)."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["registry_compose"] = "registry_compose"
    summary: str = ""
    scenarios: list[RegistryComposeScenario] = Field(min_length=1)

    def run(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        reg = resolve_registry(registry)
        results: dict[str, list[str]] = {}
        for scenario in self.scenarios:
            parent = ExecutionGraph(goal=scenario.id)
            for tile in scenario.tiles:
                template = reg.get(tile.recipe)
                if template is None:
                    raise KeyError(f"unknown recipe {tile.recipe!r}")
                child, embed = template.tile(
                    GraphTemplateParams(goal=tile.recipe, instance_key=tile.key),
                    parent_node_id=f"embed_{tile.key}",
                )
                if tile.forge_version:
                    child.template_version = tile.forge_version
                    embed = embed.model_copy(update={"subgraph": child.checkpoint()})
                parent.add_node(embed)
            for node_id in scenario.free_form_nodes:
                parent.add_node(GraphNode(id=node_id, kind="shell"))
            results[scenario.id] = reg.composition_violations(parent)
        return {"summary": self.summary, "violations": results}


_PLAN_MODELS: dict[str, type[BaseModel]] = {
    "soft_evolution": SoftEvolutionPlan,
    "port_search": PortSearchPlan,
    "registry_compose": RegistryComposePlan,
}


RecipePlanDocument = Union[
    SoftEvolutionPlan, PortSearchPlan, RegistryComposePlan
]


def load_recipe_plan(data: Mapping[str, Any]) -> RecipePlanDocument:
    kind = data.get("plan")
    if kind not in _PLAN_MODELS:
        known = ", ".join(sorted(_PLAN_MODELS))
        raise ValueError(f"unknown recipe plan {kind!r}; known: {known}")
    model = _PLAN_MODELS[str(kind)]
    return model.model_validate(dict(data))  # type: ignore[return-value]


def load_recipe_plan_path(path: str | Path) -> RecipePlanDocument:
    file_path = Path(path)
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: recipe plan root must be a mapping")
    return load_recipe_plan(raw)


def run_recipe_plan_document(
    plan: RecipePlanDocument,
    registry: GraphTemplateRegistry | None = None,
) -> dict[str, Any]:
    return plan.run(registry=registry)


class RecipePlanCommand(BaseModel):
    """CLI verb body: ``path`` to a plan file, or inline ``plan:`` document."""

    model_config = ConfigDict(extra="allow")

    path: str | None = None
    plan: PlanKind | None = None

    @model_validator(mode="after")
    def _path_or_inline(self) -> RecipePlanCommand:
        if self.path:
            return self
        if not self.plan:
            raise ValueError("recipe_plan requires path= or plan=")
        return self

    def resolve_and_run(
        self,
        *,
        base_dir: Path | None = None,
        registry: GraphTemplateRegistry | None = None,
    ) -> dict[str, Any]:
        if self.path:
            file_path = Path(self.path)
            if not file_path.is_absolute():
                root = base_dir if base_dir is not None else Path.cwd()
                file_path = (root / file_path).resolve()
            document = load_recipe_plan_path(file_path)
        else:
            document = load_recipe_plan(self.model_dump(exclude={"path"}))
        return run_recipe_plan_document(document, registry=registry)


__all__ = [
    "PortSearchPlan",
    "RecipePlanCommand",
    "RegistryComposePlan",
    "SoftEvolutionPlan",
    "load_recipe_plan",
    "load_recipe_plan_path",
    "run_recipe_plan_document",
]
