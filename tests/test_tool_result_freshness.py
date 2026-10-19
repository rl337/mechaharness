"""Tool-result provenance and staleness rejection (MH-PA-01)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mechaharness.core.types import ToolResult
from mechaharness.tool_result_freshness import (
    ToolResultFreshnessPolicy,
    is_stale,
    reject_if_stale,
)

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)

_CASES = [
    # id, result fields, policy kwargs, expected reason
    ("no_metadata", {}, {}, None),
    ("expires_future", {"expires_at": "2026-10-18T13:00:00Z"}, {}, None),
    ("expires_past", {"expires_at": "2026-10-18T11:00:00Z"}, {}, "expired"),
    ("expires_exactly_now", {"expires_at": "2026-10-18T12:00:00Z"}, {}, "expired"),
    ("opaque_expiry_ignored", {"expires_at": "soon"}, {}, None),
    ("age_ok", {"observed_at": "2026-10-18T11:30:00Z"}, {"max_age_seconds": 3600}, None),
    (
        "age_too_old",
        {"observed_at": "2026-10-10T12:00:00Z"},
        {"max_age_seconds": 86_400},
        "too_old",
    ),
    (
        "age_uses_fetched_at",
        {"fetched_at": "2026-10-10T12:00:00Z"},
        {"max_age_seconds": 60},
        "too_old",
    ),
    ("age_without_stamp_passes", {}, {"max_age_seconds": 60}, None),
    ("missing_source", {}, {"require_provenance": True}, "missing_source"),
    ("has_source", {"source": "crm"}, {"require_provenance": True}, None),
]


@pytest.mark.parametrize(
    ("case_id", "fields", "policy", "reason"), _CASES, ids=[c[0] for c in _CASES]
)
def test_freshness_policy_matrix(
    case_id: str, fields: dict, policy: dict, reason: str | None
) -> None:
    del case_id
    result = ToolResult(tool_call_id="c", content="payload", **fields)
    pol = ToolResultFreshnessPolicy(**policy)
    assert pol.stale_reason(result, now=NOW) == reason
    assert pol.is_stale(result, now=NOW) is (reason is not None)
    out = pol.reject_if_stale(result, now=NOW)
    if reason is None:
        assert out is result and not out.is_error
    else:
        assert out.is_error and out.content.startswith(f"stale_tool_result:{reason}")
        assert out.tool_call_id == "c"
        assert result.content == "payload"  # input not mutated


def test_module_helpers_use_expiry_only() -> None:
    old = ToolResult(tool_call_id="c", content="x", observed_at="2000-01-01T00:00:00Z")
    assert is_stale(old, now=NOW) is False
    expired = ToolResult(tool_call_id="c", content="x", expires_at="2026-01-01T00:00:00Z")
    assert is_stale(expired, now=NOW) is True
    assert reject_if_stale(expired, now=NOW).is_error is True


def test_tool_result_fields_are_optional_and_backward_compatible() -> None:
    result = ToolResult(tool_call_id="c", content="x")
    assert (result.source, result.observed_at, result.fetched_at, result.expires_at) == (None,) * 4
