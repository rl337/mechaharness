"""Cost units for inference (and later tools).

Ability is a five-step scale; higher ability costs more. The accountant
counts, keeps a ledger, and emits ``core:cost`` on the shared EventLog.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel, Field

from mechaharness.core.events import Cost, Event, EventLog, event_type_key


class Ability(str, Enum):
    """How capable a completer is at a given kind of work."""

    SIMPLE = "simple"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    PROFICIENT = "proficient"
    ADVANCED = "advanced"

    @property
    def rank(self) -> int:
        order = (
            Ability.SIMPLE,
            Ability.BASIC,
            Ability.INTERMEDIATE,
            Ability.PROFICIENT,
            Ability.ADVANCED,
        )
        return order.index(self) + 1

    @property
    def units(self) -> int:
        """Cost units: 1, 2, 4, 8, 16."""
        return 1 << (self.rank - 1)


class CapabilityKind(str, Enum):
    """Kinds of work a completer can perform (aligned with model skills)."""

    CODE = "code"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"


class Capability(BaseModel):
    kind: CapabilityKind
    level: Ability


class CapabilityProfile(BaseModel):
    """Declared skills of a completer. Cost is the sum of each capability's units."""

    capabilities: list[Capability] = Field(default_factory=list)

    def units(self) -> int:
        if not self.capabilities:
            return Ability.SIMPLE.units
        return sum(item.level.units for item in self.capabilities)


class CostEntry(BaseModel):
    kind: str
    name: str
    units: int
    capabilities: list[Capability] = Field(default_factory=list)


class CostReport(BaseModel):
    units: int = 0
    entries: list[CostEntry] = Field(default_factory=list)

    def add(self, entry: CostEntry) -> None:
        self.entries.append(entry)
        self.units += entry.units


def inference_cost_entry(name: str, profile: CapabilityProfile) -> CostEntry:
    return CostEntry(
        kind="inference",
        name=name,
        units=profile.units(),
        capabilities=list(profile.capabilities),
    )


class CostAccountant(ABC):
    """Price one inference call and keep a ledger."""

    @abstractmethod
    def price_inference(
        self,
        name: str,
        profile: CapabilityProfile,
        *,
        agent_id: str = "",
        run_id: str = "",
        parent_agent_id: str | None = None,
    ) -> CostEntry:
        """Units for one completer call."""

    @abstractmethod
    def report(self) -> CostReport:
        """Accumulated ledger for this accountant instance."""


class InMemoryCostAccountant(CostAccountant):
    """Prices from the capability profile; keeps a ledger; emits ``core:cost``."""

    def __init__(self, event_log: EventLog | None = None) -> None:
        self._event_log = event_log
        self._report = CostReport()

    def price_inference(
        self,
        name: str,
        profile: CapabilityProfile,
        *,
        agent_id: str = "",
        run_id: str = "",
        parent_agent_id: str | None = None,
    ) -> CostEntry:
        entry = inference_cost_entry(name, profile)
        self._report.add(entry)
        if self._event_log is not None and agent_id and run_id:
            self._event_log.emit(
                Event(
                    type=event_type_key(Cost),
                    agent_id=agent_id,
                    run_id=run_id,
                    parent_agent_id=parent_agent_id,
                    payload={"kind": entry.kind, "name": entry.name, "units": entry.units},
                )
            )
        return entry

    def report(self) -> CostReport:
        return self._report


def default_capability_profile() -> CapabilityProfile:
    """Pass-through / unknown completer: simple reasoning only."""
    return CapabilityProfile(
        capabilities=[Capability(kind=CapabilityKind.REASONING, level=Ability.SIMPLE)]
    )
