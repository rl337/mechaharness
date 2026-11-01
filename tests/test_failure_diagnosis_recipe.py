"""Static tests for failure_diagnosis / gastronomic M6 increment 5."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mechaharness.failure_diagnosis import (
    assemble_diagnosis,
    classify_failure_evidence,
    extract_diagnosis_constraints,
    validate_diagnosis,
)
from mechaharness.graph_templates import (
    FailureDiagnosisTemplate,
    GastronomicGuidedDevelopmentTemplate,
    GraphTemplateParams,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for


@dataclass(frozen=True)
class _ClassifyCase:
    id: str
    text: str
    failure_class: str
    next_experiment: str


_CLASSIFY_CASES: tuple[_ClassifyCase, ...] = (
    _ClassifyCase(
        "syntax",
        "python_parses failed: SyntaxError invalid syntax",
        "syntax",
        "fix_parse_error_at_cited_span",
    ),
    _ClassifyCase(
        "tool_protocol",
        "malformed tool_call JSON function call",
        "tool_protocol",
        "repair_tool_call_shape_or_schema",
    ),
    _ClassifyCase(
        "budget",
        "budget exhausted: timeout max_tokens",
        "budget",
        "raise_budget_or_narrow_work",
    ),
    _ClassifyCase(
        "runtime",
        "Traceback ModuleNotFoundError: exception: boom",
        "runtime",
        "fix_exception_at_cited_frame",
    ),
    _ClassifyCase(
        "scope",
        "refused: scope_escape outside allowed paths",
        "scope",
        "refuse_or_replan_within_allowed_paths",
    ),
    _ClassifyCase(
        "unknown",
        "something odd happened in the host",
        "unknown",
        "gather_more_host_evidence_before_retry",
    ),
)


def test_failure_diagnosis_in_default_catalog() -> None:
    names = default_graph_templates().names()
    assert "failure_diagnosis" in names


def test_failure_diagnosis_topology() -> None:
    template = FailureDiagnosisTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Diagnose verify failure",
            inputs={
                "goal": "Diagnose verify failure",
                "verification_report": {
                    "version": "1",
                    "status": "failed",
                    "failures": ["pytest exit 1"],
                },
            },
        )
    )
    assert graph.template_name == "failure_diagnosis"
    assert sorted(graph.nodes) == [
        "classify",
        "constrain",
        "publish",
        "seed",
        "validate",
    ]
    comps = node_components_for(graph, template=template)
    soft = {c.soft_point_name for c in comps if c.kind == "soft_point"}
    assert "diagnose_payload" in soft


def test_gastronomic_tiles_diagnose_after_verify() -> None:
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
    assert "verify_tile" in graph.nodes
    assert "diagnose_tile" in graph.nodes
    assert graph.nodes["diagnose_tile"].subgraph


def test_classify_semantics_from_pytest_failure() -> None:
    constraints = extract_diagnosis_constraints(
        verification_report={
            "version": "1",
            "status": "failed",
            "failures": ["verify_runs[0] pytest tests/test_arithmetic.py: exit 1 != 0"],
            "verify_runs": [],
            "regression": {"unchanged_invariants_ok": True, "invariants_checked": 0},
            "provenance": {"slice_id": "arithmetic"},
        }
    )
    assert constraints["evidence"]
    classification = classify_failure_evidence(constraints["evidence"])
    assert classification["failure_class"] == "semantics"
    diagnosis = assemble_diagnosis(constraints=constraints, classification=classification)
    assert diagnosis["status"] == "ok"
    assert diagnosis["failure_class"] == "semantics"
    assert diagnosis["next_experiment"] == "adjust_behavior_to_satisfy_failing_check"
    assert validate_diagnosis(diagnosis)["ok"] is True


def test_classify_regression_and_repeat_changes_experiment() -> None:
    constraints = extract_diagnosis_constraints(
        verification_report={
            "version": "1",
            "status": "failed",
            "failures": [],
            "verify_runs": [],
            "regression": {
                "unchanged_invariants_ok": False,
                "invariants_checked": 1,
            },
        },
        prior_attempts=[{"failure_class": "regression", "next_experiment": "x"}],
    )
    classification = classify_failure_evidence(constraints["evidence"])
    assert classification["failure_class"] == "regression"
    diagnosis = assemble_diagnosis(constraints=constraints, classification=classification)
    assert diagnosis["next_experiment"] == "change_strategy_after_repeat_regression"


def test_green_verification_yields_none_class() -> None:
    constraints = extract_diagnosis_constraints(
        verification_report={
            "version": "1",
            "status": "ok",
            "failures": [],
            "verify_runs": [{"ok": True, "failures": []}],
            "regression": {"unchanged_invariants_ok": True, "invariants_checked": 1},
        }
    )
    classification = classify_failure_evidence(constraints["evidence"])
    diagnosis = assemble_diagnosis(constraints=constraints, classification=classification)
    assert diagnosis["failure_class"] == "none"
    assert diagnosis["next_experiment"] == "continue_or_accept"
    assert validate_diagnosis(diagnosis)["ok"] is True


@pytest.mark.parametrize("case", _CLASSIFY_CASES, ids=lambda c: c.id)
def test_classify_failure_class_matrix(case: _ClassifyCase) -> None:
    classification = classify_failure_evidence([{"text": case.text}])
    assert classification["failure_class"] == case.failure_class
    diagnosis = assemble_diagnosis(
        constraints={"status": "ok", "evidence": [{"text": case.text}]},
        classification=classification,
    )
    assert diagnosis["next_experiment"] == case.next_experiment
    assert validate_diagnosis(diagnosis)["ok"] is True


def test_extract_pulls_verify_runs_and_execution_refusals() -> None:
    constraints = extract_diagnosis_constraints(
        verification_report={
            "status": "failed",
            "failures": ["  "],
            "verify_runs": [
                {
                    "ok": False,
                    "path": "src/x.py",
                    "index": 0,
                    "failures": ["text_contains missing mul"],
                },
                {"ok": True, "failures": ["ignored"]},
                "skip-me",
            ],
            "provenance": "not-a-mapping",
        },
        change_execution={
            "status": "failed",
            "slice_id": "slice-1",
            "scope_violations": ["secrets/token.txt", {"reason": "scope_escape"}],
            "refused": [{"reason": "scope_escape", "path": "out.bin"}, "bare-refuse"],
        },
        prior_attempts=["skip", {"failure_class": "scope"}],
    )
    assert constraints["status"] == "ok"
    assert constraints["slice_id"] == "slice-1"
    sources = {row["source"] for row in constraints["evidence"]}
    assert "verification.verify_runs" in sources
    assert "execution.scope_violations" in sources
    assert "execution.refused" in sources
    assert constraints["prior_attempts"] == [{"failure_class": "scope"}]


def test_extract_incomplete_when_empty_inputs() -> None:
    constraints = extract_diagnosis_constraints()
    assert constraints["status"] == "incomplete"
    assert constraints["evidence"] == []


def test_assemble_defaults_classification_and_maps_bad_class() -> None:
    diagnosis = assemble_diagnosis(
        constraints={
            "status": "failed",
            "evidence": [{"text": "unclassified noise"}],
            "prior_attempts": [],
        }
    )
    assert diagnosis["failure_class"] == "unknown"
    assert diagnosis["status"] == "failed"

    remapped = assemble_diagnosis(
        constraints={"status": "ok", "evidence": []},
        classification={"failure_class": "not-a-real-class", "confidence": 0.2},
    )
    assert remapped["failure_class"] == "unknown"
    assert remapped["suspected_cause"] == "unspecified"


def test_assemble_incomplete_when_constraints_incomplete() -> None:
    diagnosis = assemble_diagnosis(
        constraints={"status": "incomplete", "evidence": []},
        classification={
            "failure_class": "none",
            "suspected_cause": "no host-observed failures",
            "confidence": 1.0,
            "matched_rules": [],
        },
    )
    assert diagnosis["status"] == "incomplete"


def test_extract_incomplete_when_report_present_but_no_evidence() -> None:
    constraints = extract_diagnosis_constraints(
        verification_report={"status": "incomplete", "failures": []}
    )
    assert constraints["status"] == "incomplete"


@pytest.mark.asyncio
async def test_diagnosis_hard_nodes_walk_bag() -> None:
    from mechaharness.budget import Budget, BudgetPolicy
    from mechaharness.diagnosis_hard_nodes import DiagnosisHardNodeRunner
    from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
    from mechaharness.graph_executor import GraphRunContext
    from mechaharness.walk_bag import WalkBag

    bag = WalkBag()
    bag.path_put(
        "in.verification_report",
        {
            "version": "1",
            "status": "failed",
            "failures": ["pytest exit 1"],
            "verify_runs": [],
            "regression": {"unchanged_invariants_ok": True},
            "provenance": {"slice_id": "arithmetic"},
        },
    )
    runner = DiagnosisHardNodeRunner()
    context = GraphRunContext(
        graph=ExecutionGraph(goal="diag-test"),
        run_id="diag-test",
        agent_id="a",
        budget=Budget(BudgetPolicy.unlimited()),
        bag=bag,
    )

    for kind, dest, reads in (
        (
            "diagnosis_constrain",
            "acc.diagnosis.constraints",
            {
                "verification_report": "in.verification_report",
                "prior_attempts": "in.prior_attempts",
            },
        ),
        (
            "diagnosis_classify",
            "acc.diagnosis.classification",
            {"constraints": "acc.diagnosis.constraints"},
        ),
        (
            "diagnosis_publish",
            "out.diagnosis",
            {
                "constraints": "acc.diagnosis.constraints",
                "classification": "acc.diagnosis.classification",
            },
        ),
        (
            "diagnosis_validate",
            "acc.diagnosis.validation",
            {"source": "out.diagnosis"},
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

    diagnosis = bag.path_get("out.diagnosis")
    assert diagnosis["failure_class"] == "semantics"
    assert bag.path_get("acc.diagnosis.validation")["ok"] is True

    with pytest.raises(ValueError, match="unknown diagnosis"):
        DiagnosisHardNodeRunner(kinds=["not_a_kind"])
    with pytest.raises(ValueError, match="at least one"):
        DiagnosisHardNodeRunner(kinds=[])


def test_validate_diagnosis_reports_schema_errors() -> None:
    report = validate_diagnosis(
        {
            "version": "0",
            "status": "weird",
            "failure_class": "none",
            "evidence": [{"text": "still present"}],
            "suspected_cause": "",
            "next_experiment": "",
            "confidence": "nope",
            "prior_attempts": {},
        }
    )
    assert report["ok"] is False
    paths = {e["path"] for e in report["errors"]}
    assert paths >= {
        "version",
        "status",
        "failure_class",
        "suspected_cause",
        "next_experiment",
        "confidence",
        "prior_attempts",
    }

    report2 = validate_diagnosis(
        {
            "version": "1",
            "status": "ok",
            "failure_class": "not-real",
            "evidence": "nope",
            "suspected_cause": "x",
            "next_experiment": "y",
            "confidence": 1.5,
            "prior_attempts": [],
        }
    )
    paths2 = {e["path"] for e in report2["errors"]}
    assert "failure_class" in paths2
    assert "evidence" in paths2
    assert "confidence" in paths2
