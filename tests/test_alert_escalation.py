"""Deterministic once/repeated/persistent alert escalation (MH-PA-06)."""

from __future__ import annotations

import pytest

from mechaharness.alert_escalation import (
    AlertEscalationPolicy,
    AlertOccurrenceCounter,
)

_CASES = [
    ("first_sighting_logs", {}, "disk", 1, "log"),
    ("zero_is_log", {}, "disk", 0, "log"),
    ("second_sighting_surfaces", {}, "disk", 2, "surface"),
    ("below_persistent_surfaces", {}, "disk", 4, "surface"),
    ("fifth_proposes", {}, "disk", 5, "propose"),
    ("tuned_thresholds", {"repeated_at": 3, "persistent_at": 4}, "disk", 3, "surface"),
    ("override_wins", {"overrides": {"disk": (1, 2)}}, "disk", 1, "surface"),
    ("override_is_per_alert", {"overrides": {"disk": (1, 2)}}, "net", 1, "log"),
]


@pytest.mark.parametrize(
    ("case_id", "kwargs", "alert", "count", "stage"), _CASES, ids=[c[0] for c in _CASES]
)
def test_stage_is_a_pure_function_of_the_count(
    case_id: str, kwargs: dict, alert: str, count: int, stage: str
) -> None:
    del case_id
    assert AlertEscalationPolicy(**kwargs).evaluate(alert, count) == stage


@pytest.mark.parametrize(
    "kwargs",
    [
        {"repeated_at": 0},
        {"repeated_at": 3, "persistent_at": 3},
        {"overrides": {"x": (4, 2)}},
    ],
)
def test_unordered_thresholds_are_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError, match="repeated < persistent"):
        AlertEscalationPolicy(**kwargs)


def test_counter_walks_the_ladder_and_can_be_cleared() -> None:
    counter = AlertOccurrenceCounter(AlertEscalationPolicy(repeated_at=2, persistent_at=3))
    assert [counter.record("a") for _ in range(4)] == ["log", "surface", "propose", "propose"]
    assert counter.record("b") == "log"
    counter.clear("a")
    assert counter.count("a") == 0
    assert counter.record("a") == "log"
