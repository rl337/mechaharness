"""Config hooks for host-owned promotion policy and evolution campaigns (MH-SR-09)."""

from __future__ import annotations

from pyiv import get_injector

from mechaharness.core.access import GraphExecute
from mechaharness.di import MechaHarnessConfig
from mechaharness.evaluator import EvaluatorResult
from mechaharness.graph_templates import GraphTemplateRegistry, VerifyRepairTemplate
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.recipe_lifecycle.evolution_campaign_hooks import (
    EvolutionCampaignHooks,
    NoopEvolutionCampaignHooks,
)
from mechaharness.recipe_lifecycle.recipe_evolution import EvolutionProposal
from mechaharness.recipe_lifecycle.recipe_promotion_policy import (
    NoopRecipePromotionPolicy,
    RecipePromotionDecision,
    RecipePromotionPolicy,
    RecipePromotionRequest,
    promote_recipe,
)


class _BaseConfig(MechaHarnessConfig):
    def get_inference_class(self):
        return MockInferenceStrategy

    def get_harness_class(self):
        return PassThroughHarness

    def get_grants(self):
        return [GraphExecute]


class _Blocker(RecipePromotionPolicy):
    def decide(self, request: RecipePromotionRequest) -> RecipePromotionDecision:
        return RecipePromotionDecision(allowed=False, reasons=["release_freeze"])


class _Recorder(NoopEvolutionCampaignHooks):
    def __init__(self) -> None:
        self.promotions: list[tuple[str, str]] = []

    def select_workloads(self, recipe_id: str) -> list[str]:
        return [f"{recipe_id}:suite"]

    def on_promotion(self, recipe_id: str, version: str) -> None:
        self.promotions.append((recipe_id, version))


class _HostConfig(_BaseConfig):
    def __init__(self) -> None:
        self.recorder = _Recorder()
        super().__init__()

    def get_recipe_promotion_policy(self) -> RecipePromotionPolicy:
        return _Blocker()

    def get_evolution_campaign_hooks(self) -> EvolutionCampaignHooks:
        return self.recorder


def test_defaults_are_noops_bound_through_the_injector() -> None:
    injector = get_injector(_BaseConfig())
    assert isinstance(injector.inject(RecipePromotionPolicy), NoopRecipePromotionPolicy)
    hooks = injector.inject(EvolutionCampaignHooks)
    assert isinstance(hooks, NoopEvolutionCampaignHooks)
    assert hooks.select_workloads("verify_repair") == []
    assert hooks.experiment_budget("verify_repair") is None
    hooks.on_proposal(EvolutionProposal())
    hooks.on_promotion("verify_repair", "1")


def test_host_config_overrides_both_hooks() -> None:
    config = _HostConfig()
    injector = get_injector(config)
    assert isinstance(injector.inject(RecipePromotionPolicy), _Blocker)
    hooks = injector.inject(EvolutionCampaignHooks)
    assert hooks is config.recorder
    assert hooks.select_workloads("verify_repair") == ["verify_repair:suite"]


class _V2(VerifyRepairTemplate):
    version = "2"


def _registry() -> GraphTemplateRegistry:
    registry = GraphTemplateRegistry([VerifyRepairTemplate()])
    registry.add_version(_V2(), parent_version="1")
    return registry


_PASSED = EvaluatorResult(evaluator_id="held", version="1", held_out=True, passed=True)


def test_host_policy_can_block_even_with_a_passing_final_test() -> None:
    registry = _registry()
    decision = promote_recipe(
        registry,
        _Blocker(),
        RecipePromotionRequest(recipe="verify_repair", to_version="2", final_test=_PASSED),
    )
    assert decision.allowed is False and decision.reasons == ["release_freeze"]
    assert registry.active_version("verify_repair") == "1"


def test_library_final_test_gate_applies_even_when_the_host_has_no_opinion() -> None:
    registry = _registry()
    request = RecipePromotionRequest(recipe="verify_repair", to_version="2")
    refused = promote_recipe(registry, NoopRecipePromotionPolicy(), request)
    assert refused.allowed is False and "final-test gate" in refused.reasons[-1]
    assert registry.active_version("verify_repair") == "1"
    accepted = promote_recipe(
        registry,
        NoopRecipePromotionPolicy(),
        request.model_copy(update={"final_test": _PASSED}),
    )
    assert accepted.allowed is True
    assert registry.active_version("verify_repair") == "2"


def test_unknown_version_is_reported_not_raised() -> None:
    decision = promote_recipe(
        _registry(),
        NoopRecipePromotionPolicy(),
        RecipePromotionRequest(recipe="verify_repair", to_version="9", final_test=_PASSED),
    )
    assert decision.allowed is False
    assert "unknown_recipe_version" in decision.reasons[-1]


def test_on_promotion_fires_only_after_a_successful_pointer_move() -> None:
    recorder = _Recorder()
    request = RecipePromotionRequest(recipe="verify_repair", to_version="2")
    gated = request.model_copy(update={"final_test": _PASSED})

    promote_recipe(_registry(), _Blocker(), gated, recorder)
    promote_recipe(_registry(), NoopRecipePromotionPolicy(), request, recorder)  # gate refuses
    promote_recipe(
        _registry(),
        NoopRecipePromotionPolicy(),
        request.model_copy(update={"to_version": "9", "final_test": _PASSED}),
        recorder,
    )
    assert recorder.promotions == []

    promote_recipe(
        _registry(),
        NoopRecipePromotionPolicy(),
        request.model_copy(update={"final_test": _PASSED}),
        recorder,
    )
    assert recorder.promotions == [("verify_repair", "2")]
