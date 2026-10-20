"""CLI probes for former ``graph_recipes`` stories."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from mechaharness.budget import BudgetPolicy
from mechaharness.cli_verb import CliProbe
from mechaharness.core.access import (
    GraphExecute,
)
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.evaluator import (
    EvaluatorResult,
)
from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
    NodeStatus,
)
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.graph_templates import (
    FanOutAggregateTemplate,
    GraphTemplateParams,
    default_graph_templates,
)
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.host_kit import host_graph_executor
from mechaharness.inference.base import InferenceStrategy
from mechaharness.node_component import (
    embed_recipe_as_tool,
    node_components_for,
    traversal_from_events,
)
from mechaharness.objective_policy import ObjectivePolicy, aggregate_objective
from mechaharness.research import EvalProtocol, ResearchLab


async def run_demoted_template_refused(inputs: dict[str, Any]) -> dict[str, Any]:
    """Demoted templates refuse instantiate (companion to RecipeBind expand)."""
    del inputs
    demoted = FanOutAggregateTemplate()
    demoted.status = "demoted"
    refused = False
    try:
        demoted.instantiate(GraphTemplateParams(goal="nope"))
    except RuntimeError:
        refused = True
    return {"demoted_refused": refused}


async def run_traversal_contract(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    records = traversal_from_events(list(request.get("events") or []))
    kinds = {r.kind for r in records}
    actual = {
        "record_count_min": len(records),
        "has_inference": "inference" in kinds,
        "has_tool_call": "tool_call" in kinds,
        "all_have_parent": all(bool(r.parent_node_id) for r in records),
    }
    return actual


async def run_recipe_as_tool(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    child = ExecutionGraph(goal=str(request.get("child_goal") or "child"))
    child.add_node(GraphNode(id="prompt", kind="compute"))
    child.template_name = "oneshot"
    parent = ExecutionGraph(goal="parent")
    parent.add_node(
        embed_recipe_as_tool(
            child,
            parent_node_id=str(request.get("parent_node_id") or "generate_image"),
            tool_name=str(request.get("tool_name") or "generate_image"),
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
    wrap = result.graph.nodes[str(request.get("parent_node_id") or "generate_image")]
    comps = node_components_for(result.graph)
    actual = {
        "status": result.status,
        "child_run_id_nonempty": bool(wrap.payload.get("child_run_id")),
        "child_status": wrap.payload.get("child_status"),
        "has_child_graph_component": any(c.kind == "child_graph" for c in comps),
    }
    return actual


async def run_recipe_registry_versions(inputs: dict[str, Any]) -> dict[str, Any]:
    """Immutable recipe versions, lineage, evals, and a reversible pointer (MH-SR-01/05)."""
    from mechaharness.graph_templates import GraphTemplateRegistry
    request = inputs
    base = default_graph_templates().get(str(request["recipe"]))
    assert base is not None
    registry = GraphTemplateRegistry([base])
    errors: list[str] = []

    def variant(version: str) -> Any:
        return type(f"V{version}", (type(base),), {"version": version})()

    for step in request["steps"]:
        op = step["op"]
        try:
            if op == "add_version":
                registry.add_version(
                    variant(step["version"]), parent_version=step.get("parent_version")
                )
            elif op == "promote":
                registry.promote(base.name, step["version"])
            elif op == "rollback":
                registry.rollback(base.name)
            elif op == "attach_evaluation":
                registry.attach_evaluation(base.name, step["version"], step["result"])
            else:
                raise AssertionError(f"unknown registry op {op!r}")
        except (KeyError, ValueError) as exc:
            errors.append(f"{op}:{type(exc).__name__}")
    actual = {
        "active_version": registry.active_version(base.name),
        "versions": registry.versions(base.name),
        "lineage": registry.lineage(base.name),
        "evaluation_counts": {
            v: len(registry.evaluations(base.name, v)) for v in registry.versions(base.name)
        },
        "errors": errors,
    }
    return actual


async def run_soft_point_evolution_allowlist(inputs: dict[str, Any]) -> dict[str, Any]:
    """Only declared evolvable soft points may be rewritten (MH-SR-03)."""
    request = inputs
    registry = default_graph_templates()
    outcomes: dict[str, str] = {}
    for attempt in request["attempts"]:
        template = registry.get(attempt["recipe"])
        assert template is not None
        try:
            template.assert_evolution_allowed(attempt["changed"])
            outcomes[attempt["id"]] = "allowed"
        except ValueError:
            outcomes[attempt["id"]] = "refused"
    evolvable = {
        name: (registry.get(name).evolvable_soft_point_names())  # type: ignore[union-attr]
        for name in request["recipes"]
    }
    return {"outcomes": outcomes, "evolvable": evolvable}


async def run_registry_only_compose(inputs: dict[str, Any]) -> dict[str, Any]:
    """Production graphs compose only registered recipes (MH-SR-02)."""
    request = inputs
    registry = default_graph_templates()
    results: dict[str, list[str]] = {}
    for scenario in request["scenarios"]:
        parent = ExecutionGraph(goal=scenario["id"])
        for tile in scenario.get("tiles", []):
            template = registry.get(tile["recipe"])
            assert template is not None
            child, embed = template.tile(
                GraphTemplateParams(goal=tile["recipe"], instance_key=tile["key"]),
                parent_node_id=f"embed_{tile['key']}",
            )
            if tile.get("forge_version"):
                child.template_version = tile["forge_version"]
                embed = embed.model_copy(update={"subgraph": child.checkpoint()})
            parent.add_node(embed)
        for node_id in scenario.get("free_form_nodes", []):
            parent.add_node(GraphNode(id=node_id, kind="shell"))
        results[scenario["id"]] = registry.composition_violations(parent)
    return {"violations": results}


async def run_recipe_final_test_gate(inputs: dict[str, Any]) -> dict[str, Any]:
    """Promotion needs a passing held-out final-test result (MH-SR-07)."""
    from mechaharness.evaluator import FinalTestGateError
    request = inputs
    lab_outcomes: dict[str, str] = {}
    registry_outcomes: dict[str, str] = {}
    registry = default_graph_templates()
    base = registry.get("verify_repair")
    assert base is not None
    registry.add_version(type("V2", (type(base),), {"version": "2"})(), parent_version="1")
    for attempt in request["attempts"]:
        final = (
            EvaluatorResult(evaluator_id="story:final", version="1", **attempt["final_test"])
            if attempt["final_test"] is not None
            else None
        )
        lab = ResearchLab(EvalProtocol(task_split="story"), baseline_metric=0.5)
        cand = lab.propose("h", {"prompt": "v2"})
        lab.evaluate(cand, metric=0.9)
        try:
            lab.promote(cand, final_test=final)
            lab_outcomes[attempt["id"]] = "promoted"
        except FinalTestGateError:
            lab_outcomes[attempt["id"]] = "refused"
        try:
            registry.promote_with_final_test("verify_repair", "2", final_test=final)
            registry_outcomes[attempt["id"]] = "promoted"
            registry.rollback("verify_repair")
        except FinalTestGateError:
            registry_outcomes[attempt["id"]] = "refused"
    unprotected = ResearchLab(
        EvalProtocol(task_split="story", held_out_protected=False), baseline_metric=0.5
    )
    free = unprotected.propose("h", {"prompt": "v2"})
    unprotected.evaluate(free, metric=0.9)
    unprotected.promote(free)
    actual = {
        "lab": lab_outcomes,
        "registry": registry_outcomes,
        "registry_pointer_after_refusals": registry.active_version("verify_repair"),
        "unprotected_protocol_promotes": unprotected.promoted is free,
    }
    return actual


async def run_recipe_evolution_candidates(inputs: dict[str, Any]) -> dict[str, Any]:
    """Traces → bounded soft-binding candidates → objective selection (MH-SR-06)."""
    from mechaharness.eval_evidence import Claim
    from mechaharness.recipe_lifecycle.recipe_evolution import (
        RecipeTraceSummary,
        ScoredCandidate,
        propose_candidates,
        select_candidate,
    )
    request = inputs
    registry = default_graph_templates()
    summaries = [RecipeTraceSummary.model_validate(s) for s in request["summaries"]]
    proposal = propose_candidates(
        summaries, registry, allowlist=request.get("allowlist"), max_candidates=3
    )
    again = propose_candidates(
        summaries, registry, allowlist=request.get("allowlist"), max_candidates=3
    )
    policy = ObjectivePolicy.model_validate(request["objective_policy"])
    scored: list[ScoredCandidate] = []
    for row in request["scored"]:
        candidate = next(
            c for c in proposal.candidates if c.soft_bindings == {row["soft_point"]: row["value"]}
        )
        result = aggregate_objective(
            policy,
            [Claim(id=k, statement=k, status=v) for k, v in row["claims"].items()],
            metrics=row["metrics"],
        )
        scored.append(ScoredCandidate(candidate=candidate, result=result))
    picked = select_candidate(scored)
    beaten = select_candidate(scored, baseline_scalar=request["baseline_scalar"])
    actual = {
        "candidate_bindings": [c.soft_bindings for c in proposal.candidates],
        "rejected": [[r.soft_point, r.reason] for r in proposal.rejected],
        "deterministic": proposal.model_dump() == again.model_dump(),
        "graphs_synthesized": any("graph" in c.model_dump() for c in proposal.candidates),
        "selected_bindings": picked.soft_bindings if picked else None,
        "selected_over_baseline": beaten.soft_bindings if beaten else None,
    }
    return actual


async def run_recipe_port_search(inputs: dict[str, Any]) -> dict[str, Any]:
    """Typed-port search returns catalog ids only (MH-SR-04)."""
    from mechaharness.recipe_lifecycle.recipe_port_search import search_compatible_recipes
    request = inputs
    registry = default_graph_templates()
    found = {
        q["id"]: search_compatible_recipes(
            registry, q.get("required_inputs"), q.get("required_outputs")
        )
        for q in request["queries"]
    }
    actual = {
        "found": found,
        "all_catalog_ids": all(
            name in registry.names() for names in found.values() for name in names
        ),
        "undeclared_recipes_skipped": not any(
            registry.get(name).io_contract is None  # type: ignore[union-attr]
            for names in found.values()
            for name in names
        ),
    }
    return actual


async def run_evolution_ownership_split(inputs: dict[str, Any]) -> dict[str, Any]:
    """Host owns campaign and promotion policy; the library keeps the gates (MH-SR-09)."""
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
    request = inputs

    class _Freeze(RecipePromotionPolicy):
        def decide(self, request: RecipePromotionRequest) -> RecipePromotionDecision:
            return RecipePromotionDecision(allowed=False, reasons=["release_freeze"])

    class _Campaign(NoopEvolutionCampaignHooks):
        def __init__(self) -> None:
            self.promotions: list[list[str]] = []

        def on_promotion(self, recipe_id: str, version: str) -> None:
            self.promotions.append([recipe_id, version])

        def select_workloads(self, recipe_id: str) -> list[str]:
            return [f"{recipe_id}:{w}" for w in request["workloads"]]

        def experiment_budget(self, recipe_id: str) -> float | None:
            return float(request["budget"])

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
        registry = default_graph_templates()
        base = registry.get("verify_repair")
        assert base is not None
        registry.add_version(type("V2", (type(base),), {"version": "2"})(), parent_version="1")
        return registry

    passed = EvaluatorResult(evaluator_id="story:final", version="1", held_out=True, passed=True)
    ask = RecipePromotionRequest(recipe="verify_repair", to_version="2")
    blocked_registry = registry_with_v2()
    blocked = promote_recipe(
        blocked_registry,
        host.inject(RecipePromotionPolicy),
        ask.model_copy(update={"final_test": passed}),
        host_hooks,
    )
    ungated_registry = registry_with_v2()
    ungated = promote_recipe(ungated_registry, NoopRecipePromotionPolicy(), ask, host_hooks)
    allowed_registry = registry_with_v2()
    allowed = promote_recipe(
        allowed_registry,
        NoopRecipePromotionPolicy(),
        ask.model_copy(update={"final_test": passed}),
        host_hooks,
    )
    actual = {
        "default_policy_is_noop": isinstance(
            default.inject(RecipePromotionPolicy), NoopRecipePromotionPolicy
        ),
        "default_hooks": [
            default_hooks.select_workloads("verify_repair"),
            default_hooks.experiment_budget("verify_repair"),
        ],
        "host_hooks": [
            host_hooks.select_workloads("verify_repair"),
            host_hooks.experiment_budget("verify_repair"),
        ],
        "host_policy_blocks": [blocked.allowed, blocked.reasons],
        "host_block_keeps_pointer": blocked_registry.active_version("verify_repair"),
        "library_gate_without_final_test": [
            ungated.allowed,
            ungated_registry.active_version("verify_repair"),
        ],
        "promoted_with_gates_passed": [
            allowed.allowed,
            allowed_registry.active_version("verify_repair"),
        ],
        "host_hooks_saw_promotions": getattr(host_hooks, "promotions", None),
    }
    return actual




GRAPH_RECIPES_HANDLERS: dict[str, Any] = {
    "demoted_template_refused": run_demoted_template_refused,
    "traversal_contract": run_traversal_contract,
    "recipe_as_tool": run_recipe_as_tool,
    "recipe_registry_versions": run_recipe_registry_versions,
    "soft_point_evolution_allowlist": run_soft_point_evolution_allowlist,
    "registry_only_compose": run_registry_only_compose,
    "recipe_final_test_gate": run_recipe_final_test_gate,
    "recipe_evolution_candidates": run_recipe_evolution_candidates,
    "recipe_port_search": run_recipe_port_search,
    "evolution_ownership_split": run_evolution_ownership_split,
}


class GraphRecipesParams(BaseModel):
    model_config = ConfigDict(extra="allow")


def _recipe_probe(name: str, fn: Any) -> type[CliProbe]:
    class _P(CliProbe):
        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            del runtime
            assert isinstance(params, GraphRecipesParams)
            out = fn(params.model_dump())
            import inspect
            if inspect.isawaitable(out):
                out = await out
            return out

    _P.name = name
    _P.params_model = GraphRecipesParams
    _P.__name__ = f"{name}_probe"
    _P.__qualname__ = _P.__name__
    return _P


def graph_recipes_cli_probe_classes() -> dict[str, type[CliProbe]]:
    return {
        name: _recipe_probe(name, fn) for name, fn in GRAPH_RECIPES_HANDLERS.items()
    }


__all__ = [
    "GRAPH_RECIPES_HANDLERS",
    "GraphRecipesParams",
    "graph_recipes_cli_probe_classes",
]
