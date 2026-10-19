"""Durable-by-contract denial memory with equivalent-action keys (MH-DOTS-05).

A denied send must not succeed by retrying through a second provider or tool.
Denials are keyed by an *action digest* over the side-effect class and target,
not over the tool or provider name, so equivalent actions collide::

    >>> from mechaharness.denial_store import (
    ...     InMemoryDenialStore, equivalent_action_digest,
    ... )
    >>> store = InMemoryDenialStore()
    >>> via_smtp = equivalent_action_digest("email.send", "bob@example.com")
    >>> via_api = equivalent_action_digest("email.send", "bob@example.com")
    >>> via_smtp == via_api
    True
    >>> _ = store.record(via_smtp, reason="user_denied", tool_name="smtp.send")
    >>> store.lookup(via_api).tool_name
    'smtp.send'
    >>> store.lookup(equivalent_action_digest("email.send", "amy@example.com")) is None
    True
    >>> store.lift(via_api)  # explicit new authorization
    True
    >>> store.lookup(via_api) is None
    True

:class:`DenialStore` is the seam: hosts bind a durable implementation (SQLite,
a service) while :class:`InMemoryDenialStore` is the process-local reference.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.model_input_manifest import content_digest


def equivalent_action_digest(
    effect_class: str, target: str, **qualifiers: Any
) -> str:
    """Digest identifying *what* was denied, independent of tool/provider name."""
    return content_digest(
        {"effect_class": effect_class, "target": target, "qualifiers": qualifiers}
    )


class DenialRecord(BaseModel):
    """One remembered denial."""

    model_config = ConfigDict(extra="allow")

    action_digest: str
    reason: str = ""
    tool_name: str | None = None
    run_id: str | None = None
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DenialStore(ABC):
    """Remember denied actions across retries, tools, and delegated paths."""

    @abstractmethod
    def record(
        self,
        action_digest: str,
        *,
        reason: str = "",
        tool_name: str | None = None,
        run_id: str | None = None,
    ) -> DenialRecord:
        """Remember a denial (idempotent: the first record wins)."""

    @abstractmethod
    def lookup(self, action_digest: str) -> DenialRecord | None:
        """Return the denial for an equivalent action, if any."""

    @abstractmethod
    def lift(self, action_digest: str) -> bool:
        """Forget a denial after new explicit authorization; True if one existed."""


class InMemoryDenialStore(DenialStore):
    """Process-local denial memory (not restart-durable)."""

    def __init__(self) -> None:
        self._records: dict[str, DenialRecord] = {}

    def record(
        self,
        action_digest: str,
        *,
        reason: str = "",
        tool_name: str | None = None,
        run_id: str | None = None,
    ) -> DenialRecord:
        existing = self._records.get(action_digest)
        if existing is not None:
            return existing
        record = DenialRecord(
            action_digest=action_digest,
            reason=reason,
            tool_name=tool_name,
            run_id=run_id,
        )
        self._records[action_digest] = record
        return record

    def lookup(self, action_digest: str) -> DenialRecord | None:
        return self._records.get(action_digest)

    def lift(self, action_digest: str) -> bool:
        return self._records.pop(action_digest, None) is not None
