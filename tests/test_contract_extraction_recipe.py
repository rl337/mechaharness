"""Static tests for contract_extraction / gastronomic M6 increment 1."""

from __future__ import annotations

from mechaharness.change_contract import (
    assemble_change_contract,
    freeze_prior_invariants,
    validate_change_contract,
)
from mechaharness.graph_templates import (
    ContractExtractionTemplate,
    GastronomicGuidedDevelopmentTemplate,
    GraphTemplateParams,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for


def test_contract_recipes_in_default_catalog() -> None:
    names = default_graph_templates().names()
    assert "contract_extraction" in names
    assert "gastronomic_guided_development" in names


def test_contract_extraction_topology() -> None:
    template = ContractExtractionTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Add multiplication",
            inputs={
                "goal": "Add multiplication",
                "workspace_inventory": {
                    "status": "found",
                    "relevant_files": [
                        {"path": "src/calc/arithmetic.py", "sha256": "abc"}
                    ],
                },
            },
        )
    )
    assert graph.template_name == "contract_extraction"
    assert sorted(graph.nodes) == [
        "assemble",
        "freeze",
        "propose",
        "seed",
        "validate",
    ]
    comps = node_components_for(graph, template=template)
    soft = {c.soft_point_name for c in comps if c.kind == "soft_point"}
    assert "propose_payload" in soft


def test_gastronomic_tiles_discovery_and_contract() -> None:
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
    assert graph.template_name == "gastronomic_guided_development"
    assert "discovery_tile" in graph.nodes
    assert "contract_tile" in graph.nodes
    assert "plan_tile" in graph.nodes
    assert "execute_tile" in graph.nodes
    assert graph.nodes["discovery_tile"].subgraph
    assert graph.nodes["contract_tile"].subgraph
    assert graph.nodes["plan_tile"].subgraph
    assert graph.nodes["execute_tile"].subgraph
    comps = node_components_for(graph, template=template)
    assert any(c.kind == "soft_point" for c in comps)
    assert any(c.kind == "child_graph" for c in comps)


def test_freeze_and_assemble_preserve_immutable_invariants() -> None:
    inventory = {
        "status": "found",
        "workspace_revision": "rev1",
        "relevant_files": [
            {
                "path": "src/calc/arithmetic.py",
                "sha256": "abc",
                "evidence_id": "verified:src/calc/arithmetic.py",
            }
        ],
        "tests": [
            {
                "path": "tests/test_arithmetic.py",
                "sha256": "def",
                "evidence_id": "verified:tests/test_arithmetic.py",
            }
        ],
        "unknowns": [],
    }
    frozen = freeze_prior_invariants(inventory, goal="Add multiplication")
    assert any(row["id"] == "preserve:src/calc/arithmetic.py" for row in frozen)
    contract = assemble_change_contract(
        goal="Add multiplication",
        inventory=inventory,
        proposed={
            "requested_behavior": "Support * operator",
            "invariants": [
                {
                    "id": "preserve:src/calc/arithmetic.py",
                    "description": "model tries to drop this",
                    "immutable": True,
                },
                {"id": "keep_cli", "description": "CLI still works"},
            ],
            "prohibited_changes": ["eval()"],
            "verification": [{"pytest": True, "path": "tests/"}],
        },
        frozen_invariants=frozen,
    )
    assert contract["status"] == "ok"
    ids = [row["id"] for row in contract["invariants"]]
    assert ids.count("preserve:src/calc/arithmetic.py") == 1
    assert "keep_cli" in ids
    assert "eval()" in contract["prohibited_changes"]
    report = validate_change_contract(contract)
    assert report["ok"] is True


def test_assemble_incomplete_when_discovery_empty() -> None:
    contract = assemble_change_contract(
        goal="Find missing feature",
        inventory={"status": "not_found", "relevant_files": [], "tests": []},
        proposed={"requested_behavior": "n/a"},
    )
    assert contract["status"] == "incomplete"
