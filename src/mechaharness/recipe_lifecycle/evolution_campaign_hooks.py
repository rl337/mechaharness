"""Host-owned evolution campaign hooks (MH-SR-09).

The AI assistant host (or another host) owns workload selection, experiment budgets, and
campaign bookkeeping. MechaHarness keeps validation: proposals are bounded by
the registry and the evolvable allowlist before any hook sees them. Bind a host
implementation with ``MechaHarnessConfig.get_evolution_campaign_hooks()``; the
default is a no-op::

    >>> from mechaharness.recipe_lifecycle.evolution_campaign_hooks import (
    ...     NoopEvolutionCampaignHooks,
    ... )
    >>> hooks = NoopEvolutionCampaignHooks()
    >>> hooks.select_workloads("verify_repair"), hooks.experiment_budget("verify_repair")
    ([], None)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from mechaharness.recipe_lifecycle.recipe_evolution import EvolutionProposal


class EvolutionCampaignHooks(ABC):
    """Seams a host fills in for evolution campaigns it owns."""

    @abstractmethod
    def select_workloads(self, recipe_id: str) -> list[str]:
        """Workload / fixture ids a campaign should evaluate ``recipe_id`` on."""

    @abstractmethod
    def experiment_budget(self, recipe_id: str) -> float | None:
        """Spend ceiling for one campaign round (``None`` = host decides later)."""

    @abstractmethod
    def on_proposal(self, proposal: EvolutionProposal) -> None:
        """Observe a validated candidate proposal (bookkeeping only)."""

    @abstractmethod
    def on_promotion(self, recipe_id: str, version: str) -> None:
        """Observe a recipe pointer move that passed the gates."""


class NoopEvolutionCampaignHooks(EvolutionCampaignHooks):
    """Default: the host runs no campaign through MechaHarness."""

    def select_workloads(self, recipe_id: str) -> list[str]:
        del recipe_id
        return []

    def experiment_budget(self, recipe_id: str) -> float | None:
        del recipe_id
        return None

    def on_proposal(self, proposal: EvolutionProposal) -> None:
        del proposal

    def on_promotion(self, recipe_id: str, version: str) -> None:
        del recipe_id, version
