"""Review-audit record composes decision + envelope audit dimensions (MH-DOTS-09, MH-PA-08)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mechaharness.core.types import ToolResult
from mechaharness.decision_log import (
    DecisionRecord,
    ReviewAuditRecord,
    summarize_recipe_audit,
)
from mechaharness.tool_result_freshness import summarize_freshness
from mechaharness.trace_envelope import TraceEnvelope


def _decision(**extra: object) -> DecisionRecord:
    base = {"eventId": "e1", "stateHash": "h", "policyVersion": "p1", "verdict": "ALLOW"}
    return DecisionRecord.model_validate({**base, **extra})


def test_new_audit_fields_are_optional_and_round_trip_by_alias() -> None:
    plain = _decision()
    assert plain.recipe_id is None and plain.approval_ids == [] and plain.freshness_summary == {}
    rich = _decision(
        recipeId="independent_review",
        recipeVersion="1",
        freshnessSummary={"fresh": 2, "stale": 1},
        approvalIds=["a1"],
        denialIds=["d1"],
        effectIds=["x1"],
    )
    dumped = rich.model_dump(by_alias=True, mode="json")
    assert dumped["recipeId"] == "independent_review"
    assert dumped["effectIds"] == ["x1"]
    assert DecisionRecord.model_validate(dumped) == rich


def test_trace_envelope_carries_the_same_dimensions_without_changing_completeness() -> None:
    env = TraceEnvelope(
        recipe_id="verify_repair",
        recipe_version="2",
        policy_revision="rev-1",
        approval_ids=["a"],
        denial_ids=["d"],
        effect_ids=["x"],
        freshness_summary={"stale": 1},
    )
    assert env.recipe_id == "verify_repair"
    assert "recipe_id" not in env.missing_fields()  # audit fields stay optional


def test_fully_attested_record_is_reconstructable() -> None:
    audit = ReviewAuditRecord.from_records(
        _decision(
            recipeId="independent_review", recipeVersion="1", approvalIds=["a1"],
            effectIds=["x1"], executedAction="email.send",
        ),
        source_trust="trusted",
        delegated_scope="env:child",
        policy_revision="rev-7",
    )
    assert audit.missing_dimensions() == []
    assert audit.reconstructable()


_MISSING = [
    (
        "bare_allow",
        {},
        {},
        ["recipe_id", "recipe_version", "policy_revision", "source_trust", "delegated_scope"],
    ),
    (
        "deny_needs_reason_and_id",
        {"verdict": "DENY", "recipeId": "r", "recipeVersion": "1"},
        {"source_trust": "trusted", "delegated_scope": "s", "policy_revision": "p"},
        ["denial_reasons", "denial_ids"],
    ),
    (
        "ask_human_needs_approval",
        {"verdict": "ASK_HUMAN", "recipeId": "r", "recipeVersion": "1"},
        {"source_trust": "trusted", "delegated_scope": "s", "policy_revision": "p"},
        ["approval_ids"],
    ),
    (
        "executed_action_needs_effect",
        {"executedAction": "email.send", "recipeId": "r", "recipeVersion": "1"},
        {"source_trust": "trusted", "delegated_scope": "s", "policy_revision": "p"},
        ["effect_ids"],
    ),
]


@pytest.mark.parametrize(
    ("case_id", "decision", "kwargs", "missing"), _MISSING, ids=[c[0] for c in _MISSING]
)
def test_missing_dimensions(case_id, decision, kwargs, missing) -> None:
    del case_id
    audit = ReviewAuditRecord.from_records(_decision(**decision), **kwargs)
    assert audit.missing_dimensions() == missing


def test_envelope_fills_gaps_and_decision_wins_on_overlap() -> None:
    env = TraceEnvelope(
        recipe_id="from_env", recipe_version="9", policy_revision="rev-env",
        capability_envelope_ref="env:42", denial_ids=["d9"],
    )
    audit = ReviewAuditRecord.from_records(_decision(recipeId="from_decision"), env)
    assert audit.recipe_id == "from_decision"
    assert audit.recipe_version == "9"
    assert audit.policy_revision == "rev-env"
    assert audit.delegated_scope == "env:42"
    assert audit.denial_ids == ["d9"]


def test_recipe_audit_rolls_up_selection_verdicts_and_freshness() -> None:
    rows = summarize_recipe_audit(
        [
            _decision(recipeId="b", recipeVersion="1", freshnessSummary={"fresh": 1, "stale": 2}),
            _decision(recipeId="a", recipeVersion="1", verdict="DENY"),
            _decision(recipeId="b", recipeVersion="1", freshnessSummary={"fresh": 3}),
            _decision(),  # no recipe selection recorded → not attributable
        ]
    )
    assert [(r.recipe_id, r.decisions) for r in rows] == [("a", 1), ("b", 2)]
    assert rows[0].verdicts == {"DENY": 1}
    assert (rows[1].fresh_evidence, rows[1].stale_evidence) == (4, 2)


def test_summarize_freshness_counts_stale_results() -> None:
    now = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
    results = [
        ToolResult(tool_call_id="a", content="x", expires_at="2026-10-18T13:00:00Z"),
        ToolResult(tool_call_id="b", content="x", expires_at="2026-10-18T11:00:00Z"),
    ]
    assert summarize_freshness(results, now=now) == {"fresh": 1, "stale": 1}
