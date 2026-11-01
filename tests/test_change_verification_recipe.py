"""Static tests for change_verification / gastronomic M6 increment 4."""

from __future__ import annotations

import hashlib
from pathlib import Path

from mechaharness.change_verification import (
    assemble_verification_report,
    check_immutable_invariants,
    extract_verification_constraints,
    run_host_verify_runs,
    validate_verification_report,
)
from mechaharness.graph_templates import (
    ChangeVerificationTemplate,
    GastronomicGuidedDevelopmentTemplate,
    GraphTemplateParams,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for


def test_change_verification_in_default_catalog() -> None:
    names = default_graph_templates().names()
    assert "change_verification" in names


def test_change_verification_topology() -> None:
    template = ChangeVerificationTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Verify multiply helper",
            inputs={
                "goal": "Verify multiply helper",
                "change_execution": {"version": "1", "status": "ok"},
                "change_contract": {"version": "1", "status": "ok"},
                "workspace": {"root": "."},
            },
        )
    )
    assert graph.template_name == "change_verification"
    assert sorted(graph.nodes) == [
        "constrain",
        "publish",
        "run",
        "seed",
        "validate",
    ]
    comps = node_components_for(graph, template=template)
    soft = {c.soft_point_name for c in comps if c.kind == "soft_point"}
    assert "verify_payload" in soft


def test_gastronomic_tiles_verify_after_execute() -> None:
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
    assert "execute_tile" in graph.nodes
    assert "verify_tile" in graph.nodes
    assert "diagnose_tile" in graph.nodes
    assert "revise_tile" in graph.nodes
    assert "accept_tile" in graph.nodes
    assert graph.nodes["verify_tile"].subgraph
    assert graph.nodes["diagnose_tile"].subgraph
    assert graph.nodes["revise_tile"].subgraph
    assert graph.nodes["accept_tile"].subgraph


def test_host_verify_runs_and_invariants(tmp_path: Path) -> None:
    arithmetic = tmp_path / "src" / "calc" / "arithmetic.py"
    parser = tmp_path / "src" / "calc" / "parser.py"
    arithmetic.parent.mkdir(parents=True)
    arithmetic.write_text(
        "def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    parser_body = "def parse(expr):\n    return expr\n"
    parser.write_text(parser_body, encoding="utf-8")
    parser_sha = hashlib.sha256(parser_body.encode()).hexdigest()

    constraints = extract_verification_constraints(
        change_contract={
            "version": "1",
            "status": "ok",
            "verification": [
                {
                    "path": "src/calc/arithmetic.py",
                    "text_contains": ["def mul"],
                    "python_parses": True,
                }
            ],
            "invariants": [
                {
                    "id": "preserve:parser",
                    "path": "src/calc/parser.py",
                    "immutable": True,
                    "sha256": parser_sha,
                }
            ],
        },
        change_execution={
            "version": "1",
            "status": "ok",
            "slice_id": "arithmetic",
            "diff": "+def mul",
            "changed_files": [{"path": "src/calc/arithmetic.py"}],
        },
    )
    assert constraints["status"] == "ok"
    assert constraints["verify_runs"]
    assert constraints["immutable_invariants"][0]["changed"] is False

    run_results = run_host_verify_runs(root=tmp_path, specs=constraints["verify_runs"])
    assert all(row["ok"] for row in run_results)
    inv = check_immutable_invariants(root=tmp_path, invariants=constraints["immutable_invariants"])
    assert inv["ok"] is True
    report = assemble_verification_report(
        constraints=constraints,
        run_results=run_results,
        invariant_report=inv,
    )
    assert report["status"] == "ok"
    assert not report["failures"]
    assert validate_verification_report(report)["ok"] is True


def test_verify_fails_when_expected_text_missing(tmp_path: Path) -> None:
    target = tmp_path / "src" / "calc" / "arithmetic.py"
    target.parent.mkdir(parents=True)
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    constraints = extract_verification_constraints(
        change_contract={
            "version": "1",
            "status": "ok",
            "verification": [{"path": "src/calc/arithmetic.py", "text_contains": ["def mul"]}],
        },
        change_execution={"version": "1", "status": "ok", "slice_id": "arithmetic"},
    )
    run_results = run_host_verify_runs(root=tmp_path, specs=constraints["verify_runs"])
    report = assemble_verification_report(constraints=constraints, run_results=run_results)
    assert report["status"] == "failed"
    assert report["failures"]
