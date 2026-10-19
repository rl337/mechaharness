"""Compatibility shim — prefer ``mechaharness.recipe_lifecycle.evolution_campaign_hooks``.

Deprecated public import path. Update call sites to the package when practical.
"""

from mechaharness.recipe_lifecycle.evolution_campaign_hooks import (
    EvolutionCampaignHooks,
    NoopEvolutionCampaignHooks,
)

__all__ = [
    "EvolutionCampaignHooks",
    "NoopEvolutionCampaignHooks",
]
