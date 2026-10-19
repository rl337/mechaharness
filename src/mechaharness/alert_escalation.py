"""Deterministic alert escalation ladder (MH-PA-06).

Models may propose what to do about an alert; code decides how far it
escalates. The ladder is count-based and has no model in the loop: a one-off
alert is logged, a repeated alert is surfaced to the operator, and a
persistent alert proposes a repair::

    >>> from mechaharness.alert_escalation import AlertEscalationPolicy
    >>> policy = AlertEscalationPolicy(repeated_at=2, persistent_at=4)
    >>> [policy.evaluate("disk_full", n) for n in (1, 2, 3, 4, 9)]
    ['log', 'surface', 'surface', 'propose', 'propose']

Per-alert thresholds override the defaults without touching the ladder::

    >>> tuned = AlertEscalationPolicy(
    ...     overrides={"disk_full": (1, 2)},
    ... )
    >>> [tuned.evaluate("disk_full", n) for n in (1, 2)]
    ['surface', 'propose']
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AlertStage = Literal["log", "surface", "propose"]

ALERT_STAGES: tuple[AlertStage, ...] = ("log", "surface", "propose")


class AlertEscalationPolicy(BaseModel):
    """Occurrence-count thresholds: once → log, repeated → surface, persistent → propose.

    ``overrides`` maps an alert id to ``(repeated_at, persistent_at)``.
    """

    model_config = ConfigDict(extra="allow")

    policy_id: str = "core:alert_escalation"
    version: str = "1"
    repeated_at: int = 2
    persistent_at: int = 5
    overrides: dict[str, tuple[int, int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _thresholds_are_ordered(self) -> AlertEscalationPolicy:
        for label, (repeated, persistent) in {
            "default": (self.repeated_at, self.persistent_at),
            **self.overrides,
        }.items():
            if not 1 <= repeated < persistent:
                raise ValueError(
                    f"alert thresholds for {label!r} need 1 <= repeated < persistent; "
                    f"got ({repeated}, {persistent})"
                )
        return self

    def thresholds_for(self, alert_id: str) -> tuple[int, int]:
        return self.overrides.get(alert_id, (self.repeated_at, self.persistent_at))

    def evaluate(self, alert_id: str, occurrence_count: int) -> AlertStage:
        """Deterministic stage for ``occurrence_count`` sightings of ``alert_id``."""
        repeated, persistent = self.thresholds_for(alert_id)
        if occurrence_count >= persistent:
            return "propose"
        if occurrence_count >= repeated:
            return "surface"
        return "log"


class AlertOccurrenceCounter:
    """Small in-memory counter that feeds :class:`AlertEscalationPolicy`.

    Hosts with durable alert state keep their own counts and call
    :meth:`AlertEscalationPolicy.evaluate` directly.
    """

    def __init__(self, policy: AlertEscalationPolicy | None = None) -> None:
        self.policy = policy or AlertEscalationPolicy()
        self._counts: dict[str, int] = {}

    def count(self, alert_id: str) -> int:
        return self._counts.get(alert_id, 0)

    def record(self, alert_id: str) -> AlertStage:
        """Count one more occurrence and return the resulting stage."""
        self._counts[alert_id] = self.count(alert_id) + 1
        return self.policy.evaluate(alert_id, self._counts[alert_id])

    def clear(self, alert_id: str) -> None:
        """Forget an alert (for example after it was resolved)."""
        self._counts.pop(alert_id, None)
