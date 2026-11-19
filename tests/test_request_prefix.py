"""Request-prefix change classification."""

from __future__ import annotations

import pytest

from mechaharness.request_prefix import classify_prefix_change, prefix_snapshot


def _snap(**kwargs: object) -> dict:
    base = {
        "tools": [{"name": "read"}],
        "policy": "Follow the workspace policy.",
        "policy_version": "1",
        "dynamic": "write the file",
    }
    base.update(kwargs)
    return prefix_snapshot(**base)  # type: ignore[arg-type]


def test_dynamic_tail_change_is_legitimate_and_stores_no_prompt() -> None:
    before = _snap()
    after = _snap(dynamic="write the other file")
    classified = classify_prefix_change(before, after, provider_metrics=True)
    assert classified["cause"] == "dynamic_tail"
    assert classified["first_changed_block"] == "dynamic"
    assert classified["legitimate"] is True
    assert classified["raw_prompt_stored"] is False
    assert "Follow the workspace policy" not in str(classified)


def test_identical_requests_match_when_provider_reports_counters() -> None:
    snap = _snap()
    classified = classify_prefix_change(snap, snap, provider_metrics=True)
    assert classified["cause"] == "match"
    assert classified["legitimate"] is True


@pytest.mark.parametrize(
    "tools,policy_version",
    [
        pytest.param([{"name": "write"}], "1", id="changed-name"),
        pytest.param([
            {"name": "read", "parameters": {"type": "object", "required": ["path"]}}
        ], "1", id="changed-schema"),
        pytest.param([], "1", id="removed-tool"),
        pytest.param([{"name": "write"}], "2", id="tool-and-policy-change"),
    ],
)
def test_changed_tool_contract_is_never_a_match(tools: list[dict], policy_version: str) -> None:
    classified = classify_prefix_change(
        _snap(), _snap(tools=tools, policy_version=policy_version), provider_metrics=True
    )
    assert classified["cause"] == "unknown"
    assert classified["first_changed_block"] == "tools"
    assert classified["legitimate"] is None
