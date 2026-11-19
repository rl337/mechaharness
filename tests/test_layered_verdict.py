"""Paired task and harness scores."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mechaharness.layered_verdict import score_layers


@dataclass(frozen=True)
class LayerCase:
    label: str
    kwargs: dict
    task: str
    harness: str
    clean: bool
    attribution: str
    infrastructure: bool


@pytest.mark.parametrize(
    "case",
    [
        LayerCase(
            label="lucky_file_hides_dropped_error",
            kwargs={"task": "pass", "harness": "fail"},
            task="pass",
            harness="fail",
            clean=False,
            attribution="none",
            infrastructure=False,
        ),
        LayerCase(
            label="faithful_harness_wrong_file",
            kwargs={"task": "fail", "harness": "pass"},
            task="fail",
            harness="pass",
            clean=False,
            attribution="none",
            infrastructure=False,
        ),
        LayerCase(
            label="missing_audit_is_unknown",
            kwargs={"task": "pass", "harness_observed": False},
            task="pass",
            harness="unknown",
            clean=False,
            attribution="none",
            infrastructure=False,
        ),
        LayerCase(
            label="both_fail_without_trace_is_hypothesis",
            kwargs={"task": "fail", "harness": "fail"},
            task="fail",
            harness="fail",
            clean=False,
            attribution="hypothesis",
            infrastructure=False,
        ),
        LayerCase(
            label="both_fail_with_trace_is_caller_asserted",
            kwargs={"task": "fail", "harness": "fail", "trace_supports_cause": True},
            task="fail",
            harness="fail",
            clean=False,
            attribution="caller_asserted",
            infrastructure=False,
        ),
        LayerCase(
            label="infrastructure_failure_is_unscored",
            kwargs={
                "task": "fail",
                "harness": "fail",
                "infrastructure_failure": True,
            },
            task="unscored",
            harness="unscored",
            clean=False,
            attribution="none",
            infrastructure=True,
        ),
    ],
    ids=lambda case: case.label,
)
def test_score_layers(case: LayerCase) -> None:
    scored = score_layers(**case.kwargs)
    assert scored["task"] == case.task
    assert scored["harness"] == case.harness
    assert scored["clean"] is case.clean
    assert scored["attribution"] == case.attribution
    assert scored["infrastructure_failure"] is case.infrastructure
