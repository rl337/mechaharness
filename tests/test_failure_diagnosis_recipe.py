"""Static tests for failure_diagnosis / gastronomic M6 increment 5."""

from __future__ import annotations

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
