"""Unit coverage for decision_plane runtime (DP-01..09)."""

from __future__ import annotations

import pytest

from mechaharness.decision_plane_runtime import (
    build_decision_plane_telemetry,
    compare_shadow_decision,
    project_decision_state,
    run_decision_plane_policy,
)
from mechaharness.graph_templates import DecisionPlaneTemplate, GraphTemplateParams


@pytest.mark.asyncio
async def test_projection_omits_unlisted_keys() -> None:
    proj = project_decision_state(
        {"ticket_id": "T-1", "secret": "x", "channel": "email"},
        project_keys=["ticket_id", "channel"],
        facts={"amount_cents": 10},
    )
    assert proj.state == {"ticket_id": "T-1", "channel": "email"}
    assert "secret" not in proj.state
    assert proj.facts_fingerprint


@pytest.mark.asyncio
async def test_policy_batch_and_escalation() -> None:
    questions = [
        {
            "id": "team",
            "kind": "choice",
            "options": [{"id": "billing"}, {"id": "technical"}],
            "allowed_actions": ["billing", "technical"],
        },
        {"id": "risk", "kind": "score", "min": 0, "max": 1},
    ]
    ok = await run_decision_plane_policy(
        questions=questions,
        answers={"team": "billing", "risk": 0.2},
        confidence=0.95,
        confidence_floor=0.7,
    )
    assert ok.final_action == "billing"
    assert ok.batch_invocation_count == 1
    low = await run_decision_plane_policy(
        questions=questions,
        answers={"team": "billing", "risk": 0.2},
        confidence=0.2,
        confidence_floor=0.7,
    )
    assert low.escalate and low.escalation_reason == "confidence_below_floor"
    bad = await run_decision_plane_policy(
        questions=questions,
        answers={"team": "legal", "risk": 0.1},
        confidence=0.99,
        confidence_floor=0.7,
    )
    assert bad.escalate and bad.escalation_reason == "choice_not_allowed"


@pytest.mark.asyncio
async def test_shadow_does_not_control() -> None:
    questions = [
        {
            "id": "team",
            "kind": "choice",
            "options": [{"id": "billing"}, {"id": "technical"}],
            "allowed_actions": ["billing", "technical"],
        }
    ]
    cmp = await compare_shadow_decision(
        questions=questions,
        production_answers={"team": "billing"},
        shadow_answers={"team": "technical"},
        confidence=0.9,
        confidence_floor=0.7,
    )
    assert cmp.production.final_action == "billing"
    assert cmp.shadow_controls_execution is False
    assert cmp.agreement is False


def test_telemetry_omits_raw_context() -> None:
    proj = project_decision_state(
        {"ticket_id": "T-1", "body": "pii"},
        project_keys=["ticket_id"],
        facts={},
    )
    tel = build_decision_plane_telemetry(
        questions=[{"id": "team"}],
        projection=proj,
        policy=None,
        model_ref="flavor:x",
        raw_context={"body": "pii"},
    )
    dumped = tel.model_dump(mode="json")
    assert "body" not in dumped
    assert "raw_context" not in dumped
    assert tel.projection_fingerprint


def test_decision_model_soft_point_not_param_count() -> None:
    template = DecisionPlaneTemplate()
    names = {p.name for p in template.soft_points}
    assert "decision_model" in names
    assert "param_count" not in template.describe()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="t",
            inputs={
                "state_projection": {"ticket_id": "T-1"},
                "questions": [
                    {
                        "id": "team",
                        "kind": "choice",
                        "options": [{"id": "billing"}],
                        "allowed_actions": ["billing"],
                    }
                ],
            },
            soft_bindings={"decision_model": "flavor:local_decision"},
        )
    )
    assert graph.nodes["ask_batch"].payload["model_ref"] == "flavor:local_decision"
