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
    "evolution_ownership",
    "recipe_as_tool",
    "traversal_contract",
    "demoted_refuse",
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
        private = GraphTemplateRegistry({base.name: base})
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


class EvolutionOwnershipPlan(BaseModel):
    """Host owns campaign/promotion policy; library keeps gates (MH-SR-09)."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["evolution_ownership"] = "evolution_ownership"
    summary: str = ""
    recipe: str = "verify_repair"
    workloads: list[str] = Field(min_length=1)
    budget: float

    def run(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        from mechaharness.core.access import GraphExecute
        from mechaharness.di import MechaHarnessConfig, get_injector
        from mechaharness.evaluator import EvaluatorResult
        from mechaharness.graph_templates.catalog import default_graph_templates
        from mechaharness.harness.base import AbstractHarness
        from mechaharness.harness.pass_through import PassThroughHarness
        from mechaharness.inference.base import InferenceStrategy
        from mechaharness.recipe_lifecycle.evolution_campaign_hooks import (
            EvolutionCampaignHooks,
            NoopEvolutionCampaignHooks,
        )
        from mechaharness.recipe_lifecycle.recipe_promotion_policy import (
            NoopRecipePromotionPolicy,
            RecipePromotionDecision,
            RecipePromotionPolicy,
            RecipePromotionRequest,
            promote_recipe,
        )

        del registry
        workloads = list(self.workloads)
        budget = float(self.budget)
        recipe = self.recipe

        class _Freeze(RecipePromotionPolicy):
            def decide(self, request: RecipePromotionRequest) -> RecipePromotionDecision:
                return RecipePromotionDecision(
                    allowed=False, reasons=["release_freeze"]
                )

        class _Campaign(NoopEvolutionCampaignHooks):
            def __init__(self) -> None:
                self.promotions: list[list[str]] = []

            def on_promotion(self, recipe_id: str, version: str) -> None:
                self.promotions.append([recipe_id, version])

            def select_workloads(self, recipe_id: str) -> list[str]:
                return [f"{recipe_id}:{w}" for w in workloads]

            def experiment_budget(self, recipe_id: str) -> float | None:
                del recipe_id
                return budget

        class _Base(MechaHarnessConfig):
            def get_inference_class(self) -> type[InferenceStrategy]:
                from mechaharness.inference.mock import MockInferenceStrategy

                return MockInferenceStrategy

            def get_harness_class(self) -> type[AbstractHarness]:
                return PassThroughHarness

            def get_grants(self) -> list[object]:
                return [GraphExecute]

        class _Host(_Base):
            def get_recipe_promotion_policy(self) -> RecipePromotionPolicy:
                return _Freeze()

            def get_evolution_campaign_hooks(self) -> EvolutionCampaignHooks:
                return _Campaign()

        default = get_injector(_Base())
        host = get_injector(_Host())
        default_hooks = default.inject(EvolutionCampaignHooks)
        host_hooks = host.inject(EvolutionCampaignHooks)

        def registry_with_v2() -> Any:
            reg = default_graph_templates()
            base = reg.get(recipe)
            if base is None:
                raise KeyError(f"unknown recipe {recipe!r}")
            reg.add_version(
                type("V2", (type(base),), {"version": "2"})(), parent_version="1"
            )
            return reg

        passed = EvaluatorResult(
            evaluator_id="story:final", version="1", held_out=True, passed=True
        )
        ask = RecipePromotionRequest(recipe=recipe, to_version="2")
        blocked_registry = registry_with_v2()
        blocked = promote_recipe(
            blocked_registry,
            host.inject(RecipePromotionPolicy),
            ask.model_copy(update={"final_test": passed}),
            host_hooks,
        )
        ungated_registry = registry_with_v2()
        ungated = promote_recipe(
            ungated_registry, NoopRecipePromotionPolicy(), ask, host_hooks
        )
        allowed_registry = registry_with_v2()
        allowed = promote_recipe(
            allowed_registry,
            NoopRecipePromotionPolicy(),
            ask.model_copy(update={"final_test": passed}),
            host_hooks,
        )
        return {
            "summary": self.summary,
            "default_policy_is_noop": isinstance(
                default.inject(RecipePromotionPolicy), NoopRecipePromotionPolicy
            ),
            "default_hooks": [
                default_hooks.select_workloads(recipe),
                default_hooks.experiment_budget(recipe),
            ],
            "host_hooks": [
                host_hooks.select_workloads(recipe),
                host_hooks.experiment_budget(recipe),
            ],
            "host_policy_blocks": [blocked.allowed, blocked.reasons],
            "host_block_keeps_pointer": blocked_registry.active_version(recipe),
            "library_gate_without_final_test": [
                ungated.allowed,
                ungated_registry.active_version(recipe),
            ],
            "promoted_with_gates_passed": [
                allowed.allowed,
                allowed_registry.active_version(recipe),
            ],
            "host_hooks_saw_promotions": getattr(host_hooks, "promotions", None),
        }


class RecipeAsToolPlan(BaseModel):
    """Embed a child recipe graph as a tool node and execute it."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["recipe_as_tool"] = "recipe_as_tool"
    summary: str = ""
    parent_node_id: str = "generate_image"
    tool_name: str = "generate_image"
    child_goal: str = "oneshot"

    async def run(
        self, registry: GraphTemplateRegistry | None = None
    ) -> dict[str, Any]:
        from mechaharness.budget import BudgetPolicy
        from mechaharness.graph import NodeStatus
        from mechaharness.graph_executor import (
            CallableGraphNodeRunner,
            GraphRunContext,
            NodeOutcome,
        )
        from mechaharness.host_kit import host_graph_executor
        from mechaharness.node_component import embed_recipe_as_tool, node_components_for

        del registry

        async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
            del context
            return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

        child = ExecutionGraph(goal=self.child_goal)
        child.add_node(GraphNode(id="prompt", kind="compute"))
        child.template_name = "oneshot"
        parent = ExecutionGraph(goal="parent")
        parent.add_node(
            embed_recipe_as_tool(
                child,
                parent_node_id=self.parent_node_id,
                tool_name=self.tool_name,
            )
        )
        executor = host_graph_executor(
            runners=[CallableGraphNodeRunner(["compute"], ok)],
        )
        result = await executor.run(
            parent,
            budget_policy=BudgetPolicy.unlimited(),
            run_id="story-rat",
            skip_linkage=True,
        )
        wrap = result.graph.nodes[self.parent_node_id]
        comps = node_components_for(result.graph)
        return {
            "summary": self.summary,
            "status": result.status,
            "child_run_id_nonempty": bool(wrap.payload.get("child_run_id")),
            "child_status": wrap.payload.get("child_status"),
            "has_child_graph_component": any(c.kind == "child_graph" for c in comps),
        }


class TraversalContractPlan(BaseModel):
    """Derive traversal records from stamped events (parent_node_id required)."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["traversal_contract"] = "traversal_contract"
    summary: str = ""
    events: list[dict[str, Any]] = Field(min_length=1)

    def run(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        from mechaharness.node_component import traversal_from_events

        del registry
        records = traversal_from_events(list(self.events))
        kinds = {r.kind for r in records}
        return {
            "summary": self.summary,
            "record_count_min": len(records),
            "has_inference": "inference" in kinds,
            "has_tool_call": "tool_call" in kinds,
            "all_have_parent": all(bool(r.parent_node_id) for r in records),
        }


class DemotedRefusePlan(BaseModel):
    """Demoted templates refuse instantiate."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["demoted_refuse"] = "demoted_refuse"
    summary: str = ""
    template: str = "fan_out_aggregate"

    def run(self, registry: GraphTemplateRegistry | None = None) -> dict[str, Any]:
        from mechaharness.graph_templates.catalog import default_graph_templates

        del registry
        base = default_graph_templates().get(self.template)
        if base is None:
            raise KeyError(f"unknown template {self.template!r}")
        demoted = type(base)()
        demoted.status = "demoted"
        refused = False
        try:
            demoted.instantiate(GraphTemplateParams(goal="nope"))
        except RuntimeError:
            refused = True
        return {"summary": self.summary, "demoted_refused": refused}


_PLAN_MODELS: dict[str, type[BaseModel]] = {
    "soft_evolution": SoftEvolutionPlan,
    "port_search": PortSearchPlan,
    "registry_compose": RegistryComposePlan,
    "registry_versions": RegistryVersionsPlan,
    "final_test_gate": FinalTestGatePlan,
    "evolution_candidates": EvolutionCandidatesPlan,
    "evolution_ownership": EvolutionOwnershipPlan,
    "recipe_as_tool": RecipeAsToolPlan,
    "traversal_contract": TraversalContractPlan,
    "demoted_refuse": DemotedRefusePlan,
}


RecipePlanDocument = Union[
    SoftEvolutionPlan,
    PortSearchPlan,
    RegistryComposePlan,
    RegistryVersionsPlan,
    FinalTestGatePlan,
    EvolutionCandidatesPlan,
    EvolutionOwnershipPlan,
    RecipeAsToolPlan,
    TraversalContractPlan,
    DemotedRefusePlan,
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
) -> Any:
    """Return observation dict, or an awaitable for async plans."""
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
    ) -> Any:
        """Return an observation mapping, or an awaitable that yields one."""
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
    "DemotedRefusePlan",
    "EvolutionCandidatesPlan",
    "EvolutionOwnershipPlan",
    "FinalTestGatePlan",
    "PortSearchPlan",
    "RecipeAsToolPlan",
    "RecipePlanCommand",
    "RegistryComposePlan",
    "RegistryVersionsPlan",
    "SoftEvolutionPlan",
    "TraversalContractPlan",
    "load_recipe_plan",
    "load_recipe_plan_path",
    "run_recipe_plan_document",
]
