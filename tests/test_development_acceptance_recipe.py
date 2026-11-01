"""Static tests for development_acceptance / gastronomic M6 increment 7."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mechaharness.development_acceptance import (
    assemble_development_outcome,
    decide_acceptance_outcome,
    extract_acceptance_constraints,
    validate_development_outcome,
)
from mechaharness.graph_templates import (
    DevelopmentAcceptanceTemplate,
    GastronomicGuidedDevelopmentTemplate,
    GraphTemplateParams,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for


@dataclass(frozen=True)
class _OutcomeCase:
    id: str
    verification_status: str
    disposition: str
    outcome: str
    execution_status: str = "ok"
    scope_violations: tuple[str, ...] = ()
    coverage: dict[str, float] | None = None
    regression_ok: bool = True


_OUTCOME_CASES: tuple[_OutcomeCase, ...] = (
    _OutcomeCase("completed", "ok", "continue_or_accept", "completed"),
    _OutcomeCase("yield", "ok", "yield_guidance", "needs_guidance"),
    _OutcomeCase("retry_open", "ok", "retry", "needs_guidance"),
    _OutcomeCase("stopped", "failed", "stop", "failed"),
    _OutcomeCase(
        "scope_fail",
        "ok",
        "continue_or_accept",
        "failed",
        execution_status="failed",
        scope_violations=("secrets/x",),
    ),
    _OutcomeCase(
        "coverage_fail",
        "ok",
        "continue_or_accept",
        "failed",
        coverage={"observed": 0.4, "required": 0.8},
    ),
)


def test_development_acceptance_in_default_catalog() -> None:
    names = default_graph_templates().names()
    assert "development_acceptance" in names


def test_development_acceptance_topology() -> None:
    template = DevelopmentAcceptanceTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Accept multiply change",
            inputs={
                "goal": "Accept multiply change",
                "verification_report": {"version": "1", "status": "ok"},
                "strategy_revision": {"disposition": "continue_or_accept"},
            },
        )
    )
    assert graph.template_name == "development_acceptance"
    assert sorted(graph.nodes) == [
        "constrain",
        "decide",
        "publish",
        "seed",
        "validate",
    ]
    comps = node_components_for(graph, template=template)
    soft = {c.soft_point_name for c in comps if c.kind == "soft_point"}
    assert "accept_payload" in soft


def test_gastronomic_tiles_accept_after_revise() -> None:
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
    assert "revise_tile" in graph.nodes
    assert "accept_tile" in graph.nodes
    assert graph.nodes["accept_tile"].subgraph
    assert "publish_outcome" in graph.nodes


@pytest.mark.parametrize("case", _OUTCOME_CASES, ids=lambda c: c.id)
def test_decide_acceptance_outcome_matrix(case: _OutcomeCase) -> None:
    constraints = extract_acceptance_constraints(
        change_contract={"status": "ok"},
        verification_report={
            "version": "1",
            "status": case.verification_status,
            "failures": []
            if case.verification_status == "ok"
            else ["pytest exit 1"],
            "regression": {"unchanged_invariants_ok": case.regression_ok},
            "provenance": {"slice_id": "arithmetic"},
        },
        change_execution={
            "status": case.execution_status,
            "slice_id": "arithmetic",
            "scope_violations": list(case.scope_violations),
            "changed_files": [{"path": "src/calc/arithmetic.py"}],
        },
        strategy_revision={"disposition": case.disposition},
        coverage=case.coverage,
    )
    decision = decide_acceptance_outcome(constraints)
    assert decision["outcome"] == case.outcome
    outcome = assemble_development_outcome(constraints=constraints, decision=decision)
    assert outcome["outcome"] == case.outcome
    assert validate_development_outcome(outcome)["ok"] is True


def test_incomplete_inputs_need_guidance() -> None:
    constraints = extract_acceptance_constraints()
    assert constraints["status"] == "incomplete"
    decision = decide_acceptance_outcome(constraints)
    assert decision["outcome"] == "needs_guidance"
    outcome = assemble_development_outcome(constraints=constraints, decision=decision)
    assert outcome["status"] == "incomplete"


def test_judge_opinion_is_advisory_only() -> None:
    constraints = extract_acceptance_constraints(
        change_contract={"status": "ok"},
        verification_report={
            "status": "failed",
            "failures": ["pytest exit 1"],
            "regression": {"unchanged_invariants_ok": True},
        },
        change_execution={"status": "ok"},
        strategy_revision={"disposition": "stop"},
        judge_opinion={"verdict": "completed", "note": "looks fine"},
    )
    decision = decide_acceptance_outcome(constraints)
    assert decision["outcome"] == "failed"
    outcome = assemble_development_outcome(constraints=constraints, decision=decision)
    assert outcome["outcome"] == "failed"
    assert outcome["provenance"]["judge_opinion"]["verdict"] == "completed"


@pytest.mark.asyncio
async def test_acceptance_hard_nodes_walk_bag() -> None:
    from mechaharness.acceptance_hard_nodes import AcceptanceHardNodeRunner
    from mechaharness.budget import Budget, BudgetPolicy
    from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
    from mechaharness.graph_executor import GraphRunContext
    from mechaharness.walk_bag import WalkBag

    bag = WalkBag()
    bag.path_put("in.change_contract", {"status": "ok"})
    bag.path_put(
        "in.verification_report",
        {
            "version": "1",
            "status": "ok",
            "failures": [],
            "regression": {"unchanged_invariants_ok": True},
            "provenance": {"slice_id": "arithmetic"},
        },
    )
    bag.path_put(
        "in.change_execution",
        {"status": "ok", "slice_id": "arithmetic", "changed_files": []},
    )
    bag.path_put(
        "in.strategy_revision",
        {"disposition": "continue_or_accept"},
    )
    runner = AcceptanceHardNodeRunner()
    context = GraphRunContext(
        graph=ExecutionGraph(goal="acc-test"),
        run_id="acc-test",
        agent_id="a",
        budget=Budget(BudgetPolicy.unlimited()),
        bag=bag,
    )
    for kind, dest, reads in (
        (
            "acceptance_constrain",
            "acc.acceptance.constraints",
            {
                "change_contract": "in.change_contract",
                "verification_report": "in.verification_report",
                "change_execution": "in.change_execution",
                "strategy_revision": "in.strategy_revision",
            },
        ),
        (
            "acceptance_decide",
            "acc.acceptance.decision",
            {"constraints": "acc.acceptance.constraints"},
        ),
        (
            "acceptance_publish",
            "out.development_outcome",
            {
                "constraints": "acc.acceptance.constraints",
                "decision": "acc.acceptance.decision",
            },
        ),
        (
            "acceptance_validate",
            "acc.acceptance.validation",
            {"source": "out.development_outcome"},
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

    published = bag.path_get("out.development_outcome")
    assert published["outcome"] == "completed"
    assert bag.path_get("acc.acceptance.validation")["ok"] is True

    with pytest.raises(ValueError, match="unknown acceptance"):
        AcceptanceHardNodeRunner(kinds=["not_a_kind"])
    with pytest.raises(ValueError, match="at least one"):
        AcceptanceHardNodeRunner(kinds=[])


def test_validate_development_outcome_reports_schema_errors() -> None:
    report = validate_development_outcome(
        {
            "version": "0",
            "status": "weird",
            "outcome": "not-real",
            "reason": "",
            "gates": "nope",
            "evidence": "nope",
        }
    )
    assert report["ok"] is False
    paths = {e["path"] for e in report["errors"]}
    assert paths >= {"version", "status", "outcome", "reason", "gates", "evidence"}

    report2 = validate_development_outcome(
        {
            "version": "1",
            "status": "failed",
            "outcome": "completed",
            "reason": "x",
            "gates": {},
            "evidence": [{"text": "still failing"}],
        }
    )
    assert report2["ok"] is False
    assert {e["path"] for e in report2["errors"]} >= {"outcome", "status"}
