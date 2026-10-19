"""Recipe lifecycle: candidate evolution, promotion policy, campaign hooks, port search.

Canonical home for the recipe-evolution leaves (MH-SR-04..09); the old top-level
modules (``mechaharness.recipe_evolution`` etc.) are thin re-export
shims.
"""

from __future__ import annotations

from mechaharness.recipe_lifecycle.evolution_campaign_hooks import (
    EvolutionCampaignHooks,
    NoopEvolutionCampaignHooks,
)
from mechaharness.recipe_lifecycle.recipe_evolution import (
    EvolutionProposal,
    RecipeCandidate,
    RecipeTraceSummary,
    RejectedSuggestion,
    ScoredCandidate,
    SoftBindingSuggestion,
    propose_candidates,
    select_candidate,
    validate_candidate,
)
from mechaharness.recipe_lifecycle.recipe_port_search import (
    ANY_PORT_TYPE,
    contract_is_compatible,
    port_types_match,
    ports_satisfied,
    search_compatible_recipes,
)
from mechaharness.recipe_lifecycle.recipe_promotion_policy import (
    NoopRecipePromotionPolicy,
    RecipePromotionDecision,
    RecipePromotionPolicy,
    RecipePromotionRequest,
    promote_recipe,
)

__all__ = [
    "SoftBindingSuggestion",
    "RecipeTraceSummary",
    "RecipeCandidate",
    "RejectedSuggestion",
    "EvolutionProposal",
    "ScoredCandidate",
    "validate_candidate",
    "propose_candidates",
    "select_candidate",
    "RecipePromotionRequest",
    "RecipePromotionDecision",
    "RecipePromotionPolicy",
    "NoopRecipePromotionPolicy",
    "promote_recipe",
    "EvolutionCampaignHooks",
    "NoopEvolutionCampaignHooks",
    "ANY_PORT_TYPE",
    "port_types_match",
    "ports_satisfied",
    "contract_is_compatible",
    "search_compatible_recipes",
]
