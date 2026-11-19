"""Diagnostics vary with inputs and never synthesize promotion evidence."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from mechaharness.context_surface import run_cache_layout_experiment, run_repo_topology
from mechaharness.evaluation_surface import (
    ResearchEvaluationParams,
    run_atk_research_reject,
    run_evaluator_compose_run,
)


@pytest.mark.parametrize("enabled", [False, True])
def test_cache_layout_uses_caller_blocks_and_toggle(enabled: bool) -> None:
    result = run_cache_layout_experiment(
        {
            "enabled": enabled,
            "policy_blocks": ["my policy"],
            "relevant": ["my context"],
            "dynamic": ["my task"],
        }
    )
    layout = result["layout"]
    assert layout["stable_prefix"] == (["my policy"] if enabled else [])
    assert layout["dynamic_tail"] == (
        ["my task"] if enabled else ["my policy", "my context", "my task"]
    )
    assert result["provider_metrics_observed"] is False


def test_topology_uses_supplied_files_and_budget() -> None:
    result = run_repo_topology(
        {
            "revision": "caller:r2",
            "files": {"z.py": "def actual(): pass", "y.py": "other"},
            "budget": 1,
        }
    )
    assert [e["path"] for e in result["entries"]] == ["z.py"]
    assert result["omissions"] == ["y.py"]
    assert result["revision"] == "caller:r2"


@pytest.mark.parametrize(
    "fn",
    [
        run_cache_layout_experiment,
        run_repo_topology,
        run_evaluator_compose_run,
        run_atk_research_reject,
    ],
)
def test_diagnostics_refuse_missing_inputs(fn) -> None:
    with pytest.raises(ValidationError):
        fn({})


@pytest.mark.parametrize("status,passed", [("pass", True), ("fail", False), ("unknown", False)])
def test_evaluator_composes_supplied_claims(status: str, passed: bool) -> None:
    result = run_evaluator_compose_run(
        {
            "evaluator_id": "caller:check",
            "version": "2",
            "claims": [{"id": "check", "statement": "host check", "status": status}],
        }
    )
    assert result["passed"] is passed
    assert result["evaluator_id"] == "caller:check"
    assert result["evidence_origin"] == "caller_supplied"


@pytest.mark.parametrize(
    "case,refusal",
    [
        ("missing", "missing_final_test"),
        ("mismatched", "final_test_candidate_mismatch"),
        ("failed", "final_test_claims_not_passed"),
        ("unknown", "final_test_claims_not_passed"),
        ("changed_candidate", "final_test_candidate_mismatch"),
        ("not_held_out", "final_test_not_held_out_or_passed"),
        ("supplied", None),
    ],
)
def test_research_promotion_needs_matching_supplied_evidence(
    case: str, refusal: str | None
) -> None:
    payload = {
        "task_split": "heldout-v1",
        "baseline_metric": 0.8,
        "candidates": [{"hypothesis": "candidate", "metric": 0.9}],
        "final_test_hypothesis": "candidate",
        "final_test": {
            "evaluator_id": "caller:heldout",
            "version": "1",
            "held_out": True,
            "passed": True,
            "claims": [{"id": "task", "statement": "task passed", "status": "pass"}],
        },
    }
    payload["final_test_candidate_digest"] = ResearchEvaluationParams.model_validate(
        payload
    ).candidate_digests()["candidate"]
    body = deepcopy(payload)
    if case == "missing":
        body.pop("final_test")
    if case == "mismatched":
        body["final_test_hypothesis"] = "another"
    if case == "failed":
        body["final_test"]["claims"][0]["status"] = "fail"
    if case == "unknown":
        body["final_test"]["claims"][0]["status"] = "unknown"
    if case == "changed_candidate":
        body["candidates"][0]["change_set"] = {"changed": True}
    if case == "not_held_out":
        body["final_test"]["held_out"] = False
    result = run_atk_research_reject(body)
    assert result["promotion_refusal"] == refusal
    assert result["promoted_nonempty"] is (refusal is None)
    assert result["evidence_origin"] == "caller_supplied"
