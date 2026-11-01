"""Static tests for strategy_revision / gastronomic M6 increment 6."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mechaharness.graph_templates import (
    GastronomicGuidedDevelopmentTemplate,
    GraphTemplateParams,
    StrategyRevisionTemplate,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for
from mechaharness.strategy_revision import (
    assemble_strategy_revision,
    decide_revision_gate,
    extract_revision_constraints,
    validate_strategy_revision,
)


@dataclass(frozen=True)
class _GateCase:
    id: str
    failure_class: str
    next_experiment: str
    disposition: str
    attempts_used: int = 0
    attempts_max: int = 3
    prior: tuple[dict[str, str], ...] = ()
    strategy_changed: bool = False


_GATE_CASES: tuple[_GateCase, ...] = (
    _GateCase(
        "green",
        "none",
        "continue_or_accept",
        "continue_or_accept",
    ),
    _GateCase(
        "retry_semantics",
        "semantics",
        "adjust_behavior_to_satisfy_failing_check",
        "retry",
    ),
    _GateCase(
        "stop_budget",
        "runtime",
        "fix_exception_at_cited_frame",
        "stop",
        attempts_used=3,
        attempts_max=3,
    ),
    _GateCase(
        "change_on_repeat_marker",
        "budget",
        "change_strategy_after_repeat_budget",
        "change_strategy",
        strategy_changed=True,
    ),
    _GateCase(
        "yield_unknown",
        "unknown",
        "gather_more_host_evidence_before_retry",
        "yield_guidance",
    ),
    _GateCase(
        "yield_scope",
        "scope",
        "refuse_or_replan_within_allowed_paths",
        "yield_guidance",
    ),
    _GateCase(
        "change_on_same_experiment",
        "syntax",
        "fix_parse_error_at_cited_span",
        "change_strategy",
        prior=(
            {
                "failure_class": "syntax",
                "next_experiment": "fix_parse_error_at_cited_span",
            },
        ),
        strategy_changed=True,
    ),
)


def test_strategy_revision_in_default_catalog() -> None:
    names = default_graph_templates().names()
    assert "strategy_revision" in names


def test_strategy_revision_topology() -> None:
    template = StrategyRevisionTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Revise after verify failure",
            inputs={
                "goal": "Revise after verify failure",
                "diagnosis": {
                    "version": "1",
                    "status": "ok",
                    "failure_class": "semantics",
                    "next_experiment": "adjust_behavior_to_satisfy_failing_check",
                },
            },
        )
    )
    assert graph.template_name == "strategy_revision"
    assert sorted(graph.nodes) == [
        "constrain",
        "decide",
        "publish",
        "seed",
        "validate",
    ]
    comps = node_components_for(graph, template=template)
    soft = {c.soft_point_name for c in comps if c.kind == "soft_point"}
    assert "revise_payload" in soft


def test_gastronomic_tiles_revise_after_diagnose() -> None:
    template = GastronomicGuidedDevelopmentTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Add multiplication safely",
            inputs={
                "goal": "Add multiplication safely",
                "workspace": {"root": "."},
                "constraints": {"read_only": True},
            },
        )
    )
    assert "diagnose_tile" in graph.nodes
    assert "revise_tile" in graph.nodes
    assert "accept_tile" in graph.nodes
    assert graph.nodes["revise_tile"].subgraph
    assert graph.nodes["accept_tile"].subgraph
    assert "publish_outcome" in graph.nodes
    assert "publish_revision" in graph.nodes


@pytest.mark.parametrize("case", _GATE_CASES, ids=lambda c: c.id)
def test_decide_revision_gate_matrix(case: _GateCase) -> None:
    constraints = extract_revision_constraints(
        diagnosis={
            "version": "1",
            "status": "ok",
            "failure_class": case.failure_class,
            "next_experiment": case.next_experiment,
            "evidence": [] if case.failure_class == "none" else [{"text": "x"}],
            "provenance": {"slice_id": "arithmetic"},
        },
        change_plan={"status": "ok", "slices": [{"id": "arithmetic"}]},
        prior_attempts=list(case.prior),
        retry_budget={
            "attempts_used": case.attempts_used,
            "attempts_max": case.attempts_max,
        },
    )
    decision = decide_revision_gate(constraints)
    assert decision["disposition"] == case.disposition
    assert decision["strategy_changed"] is case.strategy_changed
    revision = assemble_strategy_revision(constraints=constraints, decision=decision)
    assert revision["disposition"] == case.disposition
    assert validate_strategy_revision(revision)["ok"] is True


def test_incomplete_diagnosis_yields_guidance() -> None:
    constraints = extract_revision_constraints()
    assert constraints["status"] == "incomplete"
    decision = decide_revision_gate(constraints)
    assert decision["disposition"] == "yield_guidance"
    revision = assemble_strategy_revision(constraints=constraints, decision=decision)
    assert revision["status"] == "incomplete"
    assert validate_strategy_revision(revision)["ok"] is True


def test_assemble_defaults_decision_and_maps_bad_disposition() -> None:
    revision = assemble_strategy_revision(
        constraints={
            "status": "failed",
            "failure_class": "runtime",
            "next_experiment": "fix_exception_at_cited_frame",
            "prior_attempts": [],
            "retry_budget": {"attempts_used": 0, "attempts_max": 3, "remaining": 3},
        },
        decision={"disposition": "not-real", "reason": "x", "next_experiment": "y"},
    )
    assert revision["disposition"] == "yield_guidance"
    assert revision["status"] == "failed"


@pytest.mark.asyncio
async def test_revision_hard_nodes_walk_bag() -> None:
    from mechaharness.budget import Budget, BudgetPolicy
    from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
    from mechaharness.graph_executor import GraphRunContext
    from mechaharness.revision_hard_nodes import RevisionHardNodeRunner
    from mechaharness.walk_bag import WalkBag

    bag = WalkBag()
    bag.path_put(
        "in.diagnosis",
        {
            "version": "1",
            "status": "ok",
            "failure_class": "semantics",
            "next_experiment": "adjust_behavior_to_satisfy_failing_check",
            "evidence": [{"text": "pytest exit 1"}],
            "provenance": {"slice_id": "arithmetic"},
        },
    )
    bag.path_put(
        "in.change_plan",
        {"status": "ok", "slices": [{"id": "arithmetic"}]},
    )
    runner = RevisionHardNodeRunner()
    context = GraphRunContext(
        graph=ExecutionGraph(goal="rev-test"),
        run_id="rev-test",
        agent_id="a",
        budget=Budget(BudgetPolicy.unlimited()),
        bag=bag,
    )

    for kind, dest, reads in (
        (
            "revision_constrain",
            "acc.revision.constraints",
            {
                "diagnosis": "in.diagnosis",
                "change_plan": "in.change_plan",
                "prior_attempts": "in.prior_attempts",
            },
        ),
        (
            "revision_decide",
            "acc.revision.decision",
            {"constraints": "acc.revision.constraints"},
        ),
        (
            "revision_publish",
            "out.strategy_revision",
            {
                "constraints": "acc.revision.constraints",
                "decision": "acc.revision.decision",
            },
        ),
        (
            "revision_validate",
            "acc.revision.validation",
            {"source": "out.strategy_revision"},
        ),
    ):
        outcome = await runner.run(
            GraphNode(
                id=kind,
                kind=kind,
                payload={
                    "reads": reads,
                    "writes": {"destination": dest},
                    "parameters": {"fail_if_invalid": True},
                },
            ),
            context=context,
        )
        assert outcome.status == NodeStatus.SUCCEEDED, outcome.error

    revision = bag.path_get("out.strategy_revision")
    assert revision["disposition"] == "retry"
    assert revision["evidence_delta_required"] is True
    assert bag.path_get("acc.revision.validation")["ok"] is True

    with pytest.raises(ValueError, match="unknown revision"):
        RevisionHardNodeRunner(kinds=["not_a_kind"])
    with pytest.raises(ValueError, match="at least one"):
        RevisionHardNodeRunner(kinds=[])


def test_validate_strategy_revision_reports_schema_errors() -> None:
    report = validate_strategy_revision(
        {
            "version": "0",
            "status": "weird",
            "disposition": "not-real",
            "next_experiment": "",
            "reason": "",
            "retry_budget": "nope",
            "prior_attempts": {},
        }
    )
    assert report["ok"] is False
    paths = {e["path"] for e in report["errors"]}
    assert paths >= {
        "version",
        "status",
        "disposition",
        "next_experiment",
        "reason",
        "evidence_delta_required",
        "strategy_changed",
        "retry_budget",
        "prior_attempts",
    }

    report2 = validate_strategy_revision(
        {
            "version": "1",
            "status": "ok",
            "disposition": "retry",
            "next_experiment": "x",
            "reason": "y",
            "evidence_delta_required": False,
            "strategy_changed": False,
            "retry_budget": {
                "attempts_used": 0,
                "attempts_max": 3,
                "remaining": 3,
            },
            "prior_attempts": [],
        }
    )
    assert report2["ok"] is False
    assert any(e["path"] == "evidence_delta_required" for e in report2["errors"])
