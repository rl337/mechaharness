"""Compatibility shim — prefer ``mechaharness.recipe_lifecycle.recipe_promotion_policy``.

Deprecated public import path. Update call sites to the package when practical.
"""

from mechaharness.recipe_lifecycle.recipe_promotion_policy import (
    NoopRecipePromotionPolicy,
    RecipePromotionDecision,
    RecipePromotionPolicy,
    RecipePromotionRequest,
    promote_recipe,
)

__all__ = [
    "RecipePromotionRequest",
    "RecipePromotionDecision",
    "RecipePromotionPolicy",
    "NoopRecipePromotionPolicy",
    "promote_recipe",
]
