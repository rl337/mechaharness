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
