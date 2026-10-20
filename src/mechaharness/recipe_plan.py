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

PlanKind = Literal[
    "soft_evolution",
    "port_search",
    "registry_compose",
    "registry_versions",
    "final_test_gate",
    "evolution_candidates",
]


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


class RegistryVersionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_version", "promote", "rollback", "attach_evaluation"]
    version: str | None = None
    parent_version: str | None = None
    result: dict[str, Any] | None = None


class RegistryVersionsPlan(BaseModel):
    """Immutable versions, lineage, evals, and pointer rollback (MH-SR-01/05)."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["registry_versions"] = "registry_versions"
    summary: str = ""
    recipe: str
    steps: list[RegistryVersionStep] = Field(min_length=1)

    def run(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        from mechaharness.graph_templates import GraphTemplateRegistry
        from mechaharness.graph_templates.catalog import default_graph_templates

        del registry  # always isolate a private registry for the script
        base = default_graph_templates().get(self.recipe)
        if base is None:
            raise KeyError(f"unknown recipe {self.recipe!r}")
        private = GraphTemplateRegistry([base])
        errors: list[str] = []

        def variant(version: str) -> Any:
            return type(f"V{version}", (type(base),), {"version": version})()

        for step in self.steps:
            try:
                if step.op == "add_version":
                    if step.version is None:
                        raise ValueError("add_version needs version=")
                    private.add_version(
                        variant(step.version), parent_version=step.parent_version
                    )
                elif step.op == "promote":
                    if step.version is None:
                        raise ValueError("promote needs version=")
                    private.promote(base.name, step.version)
                elif step.op == "rollback":
                    private.rollback(base.name)
                elif step.op == "attach_evaluation":
                    if step.version is None or step.result is None:
                        raise ValueError("attach_evaluation needs version= and result=")
                    private.attach_evaluation(base.name, step.version, step.result)
            except (KeyError, ValueError) as exc:
                errors.append(f"{step.op}:{type(exc).__name__}")
        return {
            "summary": self.summary,
            "active_version": private.active_version(base.name),
            "versions": private.versions(base.name),
            "lineage": private.lineage(base.name),
            "evaluation_counts": {
                v: len(private.evaluations(base.name, v))
                for v in private.versions(base.name)
            },
            "errors": errors,
        }


class FinalTestAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    final_test: dict[str, Any] | None = None


class FinalTestGatePlan(BaseModel):
    """Promotion needs a passing held-out final-test result (MH-SR-07)."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["final_test_gate"] = "final_test_gate"
    summary: str = ""
    recipe: str = "verify_repair"
    attempts: list[FinalTestAttempt] = Field(min_length=1)

    def run(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        from mechaharness.evaluator import EvaluatorResult, FinalTestGateError
        from mechaharness.graph_templates.catalog import default_graph_templates
        from mechaharness.research import EvalProtocol, ResearchLab

        del registry
        lab_outcomes: dict[str, str] = {}
        registry_outcomes: dict[str, str] = {}
        catalog = default_graph_templates()
        base = catalog.get(self.recipe)
        if base is None:
            raise KeyError(f"unknown recipe {self.recipe!r}")
        catalog.add_version(
            type("V2", (type(base),), {"version": "2"})(), parent_version="1"
        )
        for attempt in self.attempts:
            final = (
                EvaluatorResult(
                    evaluator_id="story:final", version="1", **attempt.final_test
                )
                if attempt.final_test is not None
                else None
            )
            lab = ResearchLab(EvalProtocol(task_split="story"), baseline_metric=0.5)
            cand = lab.propose("h", {"prompt": "v2"})
            lab.evaluate(cand, metric=0.9)
            try:
                lab.promote(cand, final_test=final)
                lab_outcomes[attempt.id] = "promoted"
            except FinalTestGateError:
                lab_outcomes[attempt.id] = "refused"
            try:
                catalog.promote_with_final_test(
                    self.recipe, "2", final_test=final
                )
                registry_outcomes[attempt.id] = "promoted"
                catalog.rollback(self.recipe)
            except FinalTestGateError:
                registry_outcomes[attempt.id] = "refused"
        unprotected = ResearchLab(
            EvalProtocol(task_split="story", held_out_protected=False),
            baseline_metric=0.5,
        )
        free = unprotected.propose("h", {"prompt": "v2"})
        unprotected.evaluate(free, metric=0.9)
        unprotected.promote(free)
        return {
            "summary": self.summary,
            "lab": lab_outcomes,
            "registry": registry_outcomes,
            "registry_pointer_after_refusals": catalog.active_version(self.recipe),
            "unprotected_protocol_promotes": unprotected.promoted is free,
        }


class EvolutionCandidatesPlan(BaseModel):
    """Traces → bounded soft-binding candidates → objective selection (MH-SR-06)."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["evolution_candidates"] = "evolution_candidates"
    summary: str = ""
    summaries: list[dict[str, Any]] = Field(min_length=1)
    allowlist: dict[str, list[str]] | None = None
    objective_policy: dict[str, Any]
    scored: list[dict[str, Any]] = Field(min_length=1)
    baseline_scalar: float

    def run(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        from mechaharness.eval_evidence import Claim
        from mechaharness.objective_policy import ObjectivePolicy, aggregate_objective
        from mechaharness.recipe_lifecycle.recipe_evolution import (
            RecipeTraceSummary,
            ScoredCandidate,
            propose_candidates,
            select_candidate,
        )

        reg = resolve_registry(registry)
        summaries = [RecipeTraceSummary.model_validate(s) for s in self.summaries]
        proposal = propose_candidates(
            summaries, reg, allowlist=self.allowlist, max_candidates=3
        )
        again = propose_candidates(
            summaries, reg, allowlist=self.allowlist, max_candidates=3
        )
        policy = ObjectivePolicy.model_validate(self.objective_policy)
        scored: list[ScoredCandidate] = []
        for row in self.scored:
            candidate = next(
                c
                for c in proposal.candidates
                if c.soft_bindings == {row["soft_point"]: row["value"]}
            )
            result = aggregate_objective(
                policy,
                [Claim(id=k, statement=k, status=v) for k, v in row["claims"].items()],
                metrics=row["metrics"],
            )
            scored.append(ScoredCandidate(candidate=candidate, result=result))
        picked = select_candidate(scored)
        beaten = select_candidate(scored, baseline_scalar=self.baseline_scalar)
        return {
            "summary": self.summary,
            "candidate_bindings": [c.soft_bindings for c in proposal.candidates],
            "rejected": [[r.soft_point, r.reason] for r in proposal.rejected],
            "deterministic": proposal.model_dump() == again.model_dump(),
            "graphs_synthesized": any(
                "graph" in c.model_dump() for c in proposal.candidates
            ),
            "selected_bindings": picked.soft_bindings if picked else None,
            "selected_over_baseline": beaten.soft_bindings if beaten else None,
        }


_PLAN_MODELS: dict[str, type[BaseModel]] = {
    "soft_evolution": SoftEvolutionPlan,
    "port_search": PortSearchPlan,
    "registry_compose": RegistryComposePlan,
    "registry_versions": RegistryVersionsPlan,
    "final_test_gate": FinalTestGatePlan,
    "evolution_candidates": EvolutionCandidatesPlan,
}


RecipePlanDocument = Union[
    SoftEvolutionPlan,
    PortSearchPlan,
    RegistryComposePlan,
    RegistryVersionsPlan,
    FinalTestGatePlan,
    EvolutionCandidatesPlan,
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
    "EvolutionCandidatesPlan",
    "FinalTestGatePlan",
    "PortSearchPlan",
    "RecipePlanCommand",
    "RegistryComposePlan",
    "RegistryVersionsPlan",
    "SoftEvolutionPlan",
    "load_recipe_plan",
    "load_recipe_plan_path",
    "run_recipe_plan_document",
]
