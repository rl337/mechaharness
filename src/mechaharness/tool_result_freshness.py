"""Reject stale tool evidence before it drives a decision (MH-PA-01).

A cached CRM row that is eight days old must not be treated as current. Tool
results may carry ``source``, ``observed_at``, ``fetched_at``, and
``expires_at``; :class:`ToolResultFreshnessPolicy` turns those into a
fail-closed verdict::

    >>> from datetime import datetime, timezone
    >>> from mechaharness.core.types import ToolResult
    >>> from mechaharness.tool_result_freshness import (
    ...     ToolResultFreshnessPolicy, is_stale, reject_if_stale,
    ... )
    >>> now = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
    >>> cached = ToolResult(
    ...     tool_call_id="c1", content="crm: open",
    ...     source="crm.cache", observed_at="2026-10-10T12:00:00Z",
    ... )
    >>> is_stale(cached, now=now)
    False
    >>> policy = ToolResultFreshnessPolicy(max_age_seconds=86_400)
    >>> policy.is_stale(cached, now=now)
    True
    >>> rejected = policy.reject_if_stale(cached, now=now)
    >>> rejected.is_error, rejected.content.startswith("stale_tool_result")
    (True, True)
    >>> live = ToolResult(
    ...     tool_call_id="c2", content="ok", expires_at="2026-10-18T13:00:00Z",
    ... )
    >>> reject_if_stale(live, now=now).is_error
    False
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from mechaharness.core.types import ToolResult
from mechaharness.iso_timestamp import parse_iso_timestamp


def _utc(now: datetime | None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


class ToolResultFreshnessPolicy(BaseModel):
    """Fail-closed freshness rules for :class:`~mechaharness.core.types.ToolResult`.

    ``expires_at`` always applies when it parses. ``max_age_seconds`` (optional)
    bounds the age of ``observed_at`` (falling back to ``fetched_at``). With
    ``require_provenance`` a result lacking ``source`` is rejected.
    """

    model_config = ConfigDict(extra="allow")

    max_age_seconds: float | None = None
    require_provenance: bool = False

    def stale_reason(
        self, result: ToolResult, *, now: datetime | None = None
    ) -> str | None:
        """Return a short reason code when ``result`` is stale, else ``None``."""
        current = _utc(now)
        if self.require_provenance and not result.source:
            return "missing_source"
        expiry = parse_iso_timestamp(result.expires_at)
        if expiry is not None and current >= expiry:
            return "expired"
        if self.max_age_seconds is not None:
            stamp = parse_iso_timestamp(result.observed_at) or parse_iso_timestamp(
                result.fetched_at
            )
            if stamp is not None and (current - stamp).total_seconds() > self.max_age_seconds:
                return "too_old"
        return None

    def is_stale(self, result: ToolResult, *, now: datetime | None = None) -> bool:
        return self.stale_reason(result, now=now) is not None

    def reject_if_stale(
        self, result: ToolResult, *, now: datetime | None = None
    ) -> ToolResult:
        """Return ``result`` unchanged, or an error copy when it is stale."""
        reason = self.stale_reason(result, now=now)
        if reason is None:
            return result
        source = result.source or "unknown"
        return result.model_copy(
            update={
                "is_error": True,
                "content": f"stale_tool_result:{reason}:source={source}",
            }
        )


def is_stale(result: ToolResult, *, now: datetime | None = None) -> bool:
    """True when ``result.expires_at`` has passed (no max-age bound)."""
    return ToolResultFreshnessPolicy().is_stale(result, now=now)


def reject_if_stale(result: ToolResult, *, now: datetime | None = None) -> ToolResult:
    """Mark an expired result as an error; otherwise return it unchanged."""
    return ToolResultFreshnessPolicy().reject_if_stale(result, now=now)


def summarize_freshness(
    results: Sequence[ToolResult],
    *,
    policy: ToolResultFreshnessPolicy | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Count ``fresh`` / ``stale`` tool results for audit records.

    The mapping feeds ``freshness_summary`` on ``DecisionRecord`` and
    ``TraceEnvelope`` so an audit sees evidence age without the transcript.
    """
    active = policy or ToolResultFreshnessPolicy()
    stale = sum(1 for r in results if active.is_stale(r, now=now))
    return {"fresh": len(results) - stale, "stale": stale}
