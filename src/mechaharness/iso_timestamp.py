"""Parse ISO-8601 timestamps used by expiry and freshness checks.

Opaque (non-ISO) strings are allowed on wire types; callers decide how to
treat values that do not parse::

    >>> from mechaharness.iso_timestamp import parse_iso_timestamp
    >>> parse_iso_timestamp("2026-10-18T12:00:00Z").isoformat()
    '2026-10-18T12:00:00+00:00'
    >>> parse_iso_timestamp("2026-10-18").tzinfo is not None
    True
    >>> parse_iso_timestamp("epoch:7") is None
    True
"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_iso_timestamp(value: str | None) -> datetime | None:
    """Return a timezone-aware datetime, or ``None`` if ``value`` is not ISO.

    Naive timestamps are interpreted as UTC.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
