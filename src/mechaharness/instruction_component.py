"""Instruction components and gotcha metrics (req 8).

June may propose gotchas during sleep/dreaming; promotion to active policy
requires evaluation. Components distinguish invariants, domain knowledge,
procedures, and learned gotchas.
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

InstructionKind = Literal["invariant", "domain", "procedure", "gotcha"]
ComponentStatus = Literal["proposed", "active", "retired", "rejected"]


class InstructionComponent(BaseModel):
    """Scarce-information instruction bundle unit."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: InstructionKind
    title: str
    body: str
    version: str = "1"
    status: ComponentStatus = "proposed"
    trigger_count: int = 0
    use_count: int = 0
    over_trigger_count: int = 0
    under_trigger_count: int = 0
    provenance: dict[str, str] = Field(default_factory=dict)

    def record_trigger(self, *, used: bool, appropriate: bool | None = None) -> None:
        self.trigger_count += 1
        if used:
            self.use_count += 1
        if appropriate is False and used:
            self.over_trigger_count += 1
        if appropriate is True and not used:
            self.under_trigger_count += 1

    def trigger_rate(self) -> float | None:
        if self.trigger_count <= 0:
            return None
        return self.use_count / self.trigger_count


class InstructionCatalog:
    """Versionable catalog; gotchas are independently appendable."""

    def __init__(self) -> None:
        self._items: dict[str, InstructionComponent] = {}

    def add(self, component: InstructionComponent) -> InstructionComponent:
        self._items[component.id] = component
        return component

    def append_gotcha(
        self,
        title: str,
        body: str,
        *,
        provenance: dict[str, str] | None = None,
    ) -> InstructionComponent:
        return self.add(
            InstructionComponent(
                kind="gotcha",
                title=title,
                body=body,
                status="proposed",
                provenance=dict(provenance or {}),
            )
        )

    def promote(self, component_id: str) -> InstructionComponent:
        item = self._items[component_id]
        item.status = "active"
        return item

    def reject(self, component_id: str) -> InstructionComponent:
        item = self._items[component_id]
        item.status = "rejected"
        return item

    def active(self, *, kind: InstructionKind | None = None) -> list[InstructionComponent]:
        items = [i for i in self._items.values() if i.status == "active"]
        if kind is not None:
            items = [i for i in items if i.kind == kind]
        return items

    def metrics(self) -> dict[str, dict[str, float | None]]:
        return {
            cid: {
                "trigger_rate": item.trigger_rate(),
                "over_trigger": float(item.over_trigger_count),
                "under_trigger": float(item.under_trigger_count),
            }
            for cid, item in self._items.items()
        }
