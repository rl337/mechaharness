"""Unit coverage for Trouble MH-CTX-ATTR surface probes."""

from __future__ import annotations

import json

from mechaharness.context_surface import (
    run_context_evidence_survival,
    run_context_structured_tool_delivery,
)


def _large_structured(*, culprit_first: bool) -> dict:
    noise = "x" * 800
    early = {"early": [{"id": "e0"}], "noise": noise}
    late = {"culprit": {"id": "late-culprit", "finding": "root-cause"}}
    if culprit_first:
        return {**late, **early}
    return {**early, **late}


def test_structured_delivery_discloses_invalid_json_after_prefix_slice() -> None:
    out = run_context_structured_tool_delivery(
        {
            "produced": _large_structured(culprit_first=False),
            "required_fields": ["culprit"],
            "max_chars": 200,
            "structured": True,
            "observation_id": "obs:1",
        }
    )
    assert out["truncated"] is True
    assert out["payload_valid"] is False
    assert out["deficit"] is True
    assert out["silent_truncate"] is False
    assert out["delivery_ok"] is False
    assert "culprit" in out["omitted_fields"]
    # Delivered bytes must not parse as complete JSON.
    try:
        json.loads(out["delivered_content"])
        raise AssertionError("expected invalid JSON after prefix slice")
    except json.JSONDecodeError:
        pass


def test_structured_delivery_disclosure_stable_when_culprit_is_early() -> None:
    """Field order must not change whether loss is disclosed under a tight budget."""
    late = run_context_structured_tool_delivery(
        {
            "produced": _large_structured(culprit_first=False),
            "required_fields": ["culprit"],
            "max_chars": 200,
            "structured": True,
        }
    )
    early = run_context_structured_tool_delivery(
        {
            "produced": _large_structured(culprit_first=True),
            "required_fields": ["culprit"],
            "max_chars": 200,
            "structured": True,
        }
    )
    assert late["deficit"] is True and early["deficit"] is True
    assert late["silent_truncate"] is False and early["silent_truncate"] is False


def test_structured_delivery_ok_when_budget_fits() -> None:
    out = run_context_structured_tool_delivery(
        {
            "produced": {"culprit": {"id": "c"}, "early": []},
            "required_fields": ["culprit"],
            "max_chars": 10_000,
            "structured": True,
        }
    )
    assert out["truncated"] is False
    assert out["payload_valid"] is True
    assert out["deficit"] is False
    assert out["delivery_ok"] is True
    assert out["omitted_fields"] == []


def test_evidence_survival_dedupes_and_flags_false_transfer() -> None:
    ok = run_context_evidence_survival(
        {
            "produced_ids": ["a", "b", "a"],
            "delivered_ids": ["a"],
            "transferred_ids": ["a"],
            "retained_ids": ["a"],
            "persisted_ids": ["a"],
        }
    )
    assert ok["produced_count"] == 2
    assert ok["transferred_count"] == 1
    assert ok["false_transfer"] is False
    assert ok["transfer_yield"] == 0.5

    bad = run_context_evidence_survival(
        {
            "produced_ids": ["a"],
            "delivered_ids": ["a"],
            "transferred_ids": ["ghost"],
        }
    )
    assert bad["false_transfer"] is True
    assert bad["false_transferred_ids"] == ["ghost"]
