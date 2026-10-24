"""Host-owned recipe promotion policy hook (MH-SR-09).

MechaHarness validates recipes, owns the registry pointer, and enforces the
held-out final-test gate. *Whether* a candidate should be promoted (campaign
results, risk appetite, release windows) belongs to the host, for example
the AI assistant host. :class:`RecipePromotionPolicy` is that seam: bind it with
``MechaHarnessConfig.get_recipe_promotion_policy()``. The default is a no-op
that expresses no opinion; the library's final-test gate still applies::

    >>> from mechaharness.evaluator import EvaluatorResult
    >>> from mechaharness.graph_templates import default_graph_templates
    >>> from mechaharness.recipe_lifecycle.recipe_promotion_policy import (
    ...     NoopRecipePromotionPolicy, RecipePromotionRequest, promote_recipe,
    ... )
    >>> registry = default_graph_templates()
    >>> request = RecipePromotionRequest(recipe="verify_repair", to_version="1")
    >>> promote_recipe(registry, NoopRecipePromotionPolicy(), request).allowed
    False
    >>> request = request.model_copy(update={"final_test": EvaluatorResult(
    ...     evaluator_id="held", version="1", held_out=True, passed=True)})
    >>> promote_recipe(registry, NoopRecipePromotionPolicy(), request).allowed
    True

Pass the Config-bound ``EvolutionCampaignHooks`` as ``hooks`` so the host
observes each successful pointer move.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.evaluator import EvaluatorResult, FinalTestGateError
from mechaharness.graph_templates.base import GraphTemplateRegistry
from mechaharness.recipe_lifecycle.evolution_campaign_hooks import EvolutionCampaignHooks


class RecipePromotionRequest(BaseModel):
    """A host-initiated promotion of ``recipe@to_version``."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    recipe: str
    to_version: str
    final_test: EvaluatorResult | None = None
    campaign_ref: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class RecipePromotionDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    allowed: bool
    reasons: list[str] = Field(default_factory=list)


class RecipePromotionPolicy(ABC):
    """Host policy deciding whether a validated candidate may be promoted."""

    @abstractmethod
    def decide(self, request: RecipePromotionRequest) -> RecipePromotionDecision:
        ...


class NoopRecipePromotionPolicy(RecipePromotionPolicy):
    """No host opinion: never blocks (library gates still apply)."""

    def decide(self, request: RecipePromotionRequest) -> RecipePromotionDecision:
        del request
        return RecipePromotionDecision(allowed=True, reasons=["no_host_policy"])


def promote_recipe(
    registry: GraphTemplateRegistry,
    policy: RecipePromotionPolicy,
    request: RecipePromotionRequest,
    hooks: EvolutionCampaignHooks | None = None,
) -> RecipePromotionDecision:
    """Host policy decides; the library validates and applies the pointer move.

    Returns the policy decision, with the final-test outcome folded into
    ``allowed`` / ``reasons``. The registry pointer moves only when both the
    host policy and the held-out final-test gate pass. After a successful move,
    ``hooks.on_promotion(recipe, to_version)`` observes it (never on a refusal).
    """
    decision = policy.decide(request)
    if not decision.allowed:
        return decision
    try:
        registry.promote_with_final_test(
            request.recipe, request.to_version, final_test=request.final_test
        )
    except FinalTestGateError as exc:
        return RecipePromotionDecision(
            allowed=False, reasons=[*decision.reasons, str(exc)]
        )
    except KeyError as exc:
        return RecipePromotionDecision(
            allowed=False, reasons=[*decision.reasons, f"unknown_recipe_version:{exc}"]
        )
    if hooks is not None:
        hooks.on_promotion(request.recipe, request.to_version)
    return decision
