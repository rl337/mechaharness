"""Compatibility shim — prefer ``mechaharness.recipe_lifecycle.recipe_evolution``.

Deprecated public import path. Update call sites to the package when practical.
"""

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
]
