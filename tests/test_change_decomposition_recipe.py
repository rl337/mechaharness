"""Static tests for change_decomposition / gastronomic M6 increment 2."""

from __future__ import annotations

from mechaharness.change_plan import (
    assemble_change_plan,
    extract_plan_constraints,
    validate_change_plan,
)
from mechaharness.graph_templates import (
    ChangeDecompositionTemplate,
    GastronomicGuidedDevelopmentTemplate,
    GraphTemplateParams,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for


def test_change_decomposition_in_default_catalog() -> None:
    names = default_graph_templates().names()
    assert "change_decomposition" in names
    assert "gastronomic_guided_development" in names


def test_change_decomposition_topology() -> None:
    template = ChangeDecompositionTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Plan multiplication",
            inputs={
                "goal": "Plan multiplication",
                "change_contract": {
                    "version": "1",
                    "status": "ok",
                    "objective": "Add multiplication",
                    "invariants": [{"id": "preserve:a.py"}],
                    "verification": [{"pytest": True, "path": "tests/"}],
                },
            },
        )
    )
    assert graph.template_name == "change_decomposition"
    assert sorted(graph.nodes) == [
        "assemble",
        "constrain",
        "propose",
        "seed",
        "validate",
    ]
    comps = node_components_for(graph, template=template)
    soft = {c.soft_point_name for c in comps if c.kind == "soft_point"}
    assert "propose_payload" in soft


def test_gastronomic_tiles_plan_after_contract() -> None:
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
    assert "discovery_tile" in graph.nodes
    assert "contract_tile" in graph.nodes
    assert "plan_tile" in graph.nodes
    assert "execute_tile" in graph.nodes
    assert graph.nodes["plan_tile"].subgraph
    assert graph.nodes["execute_tile"].subgraph
    comps = node_components_for(graph, template=template)
    assert any(c.kind == "child_graph" for c in comps)


def test_assemble_orders_slices_and_inherits_checks() -> None:
    contract = {
        "version": "1",
        "status": "ok",
        "objective": "Add multiplication",
        "invariants": [{"id": "preserve:src/calc/arithmetic.py"}],
        "prohibited_changes": ["eval()"],
        "verification": [{"pytest": True, "path": "tests/test_arithmetic.py"}],
        "provenance": {"relevant_paths": ["src/calc/arithmetic.py"]},
    }
    constraints = extract_plan_constraints(contract)
    assert "preserve:src/calc/arithmetic.py" in constraints["invariant_ids"]
    plan = assemble_change_plan(
        contract=contract,
        constraints=constraints,
        proposed={
            "slices": [
                {
                    "id": "parser",
                    "title": "Extend parser for *",
                    "scope": {"paths": ["src/calc/parser.py"]},
                    "checks": [{"pytest": True, "path": "tests/test_parser.py"}],
                    "rollback": "revert parser.py",
                    "depends_on": ["arithmetic"],
                },
                {
                    "id": "arithmetic",
                    "title": "Add multiply helper",
                    "scope": {"paths": ["src/calc/arithmetic.py"]},
                    "rollback": "revert arithmetic.py",
                    "depends_on": [],
                },
            ]
        },
    )
    assert plan["status"] == "ok"
    assert [row["id"] for row in plan["slices"]] == ["arithmetic", "parser"]
    assert plan["slices"][0]["order"] == 0
    assert plan["slices"][0]["checks"]  # inherited from contract
    assert plan["slices"][1]["depends_on"] == ["arithmetic"]
    report = validate_change_plan(plan)
    assert report["ok"] is True


def test_assemble_incomplete_without_slices() -> None:
    plan = assemble_change_plan(
        contract={
            "status": "ok",
            "objective": "Add multiplication",
            "invariants": [],
            "verification": [],
        },
        proposed={"slices": []},
    )
    assert plan["status"] == "incomplete"


def test_assemble_failed_on_cycle() -> None:
    plan = assemble_change_plan(
        contract={"status": "ok", "objective": "x", "invariants": [], "verification": []},
        proposed={
            "slices": [
                {
                    "id": "a",
                    "title": "A",
                    "scope": {"description": "a"},
                    "checks": [{"pytest": True}],
                    "rollback": "undo a",
                    "depends_on": ["b"],
                },
                {
                    "id": "b",
                    "title": "B",
                    "scope": {"description": "b"},
                    "checks": [{"pytest": True}],
                    "rollback": "undo b",
                    "depends_on": ["a"],
                },
            ]
        },
    )
    assert plan["status"] == "failed"
    report = validate_change_plan({**plan, "status": "ok"})
    assert report["ok"] is False
