"""Typed-port search returns catalog ids only (MH-SR-04)."""

from __future__ import annotations

import pytest

from mechaharness.graph_templates import GraphTemplateRegistry, default_graph_templates
from mechaharness.graph_templates.base import GraphTemplate
from mechaharness.recipe_lifecycle.recipe_port_search import (
    contract_is_compatible,
    port_types_match,
    search_compatible_recipes,
)

_SEARCH = [
    ("produces_artifact", {}, {"artifact": "object"}, ["produce_critique_refine", "verify_repair"]),
    ("accepts_scenario", {"scenario": "object"}, {}, ["safety_eval"]),
    (
        "both_ports",
        {"scenario": "object"},
        {"safety_report": "object"},
        ["safety_eval"],
    ),
    ("wrong_type", {"scenario": "string"}, {}, []),
    ("unknown_port", {"nope": "object"}, {}, []),
    ("any_matches", {"scenario": "any"}, {"safety_report": "any"}, ["safety_eval"]),
]


@pytest.mark.parametrize(
    ("case_id", "inputs", "outputs", "expected"), _SEARCH, ids=[c[0] for c in _SEARCH]
)
def test_search_over_the_default_catalog(case_id, inputs, outputs, expected) -> None:
    del case_id
    assert search_compatible_recipes(default_graph_templates(), inputs, outputs) == expected


def test_recipes_without_a_contract_are_never_candidates() -> None:
    registry = default_graph_templates()
    undeclared = [n for n in registry.names() if registry.get(n).io_contract is None]
    assert undeclared  # honest: only some shipped recipes declare ports
    assert not set(undeclared) & set(search_compatible_recipes(registry))


def test_demoted_recipes_are_skipped() -> None:
    class Demoted(GraphTemplate):
        name = "demoted_one"
        status = "demoted"
        io_contract = default_graph_templates().get("safety_eval").io_contract

        def build(self, params):  # pragma: no cover - never instantiated
            raise AssertionError

    registry = GraphTemplateRegistry([Demoted()])
    assert search_compatible_recipes(registry, {"scenario": "object"}) == []


def test_results_are_catalog_ids_not_graphs() -> None:
    result = search_compatible_recipes(default_graph_templates(), {}, {"artifact": "object"})
    assert all(isinstance(r, str) for r in result)


@pytest.mark.parametrize(
    ("offered", "required", "ok"),
    [
        ("object", "object", True),
        ("object", "string", False),
        ("any", "x", True),
        ("x", "any", True),
    ],
)
def test_port_type_matching(offered, required, ok) -> None:
    assert port_types_match(offered, required) is ok


def test_contract_compatibility_checks_both_directions() -> None:
    contract = default_graph_templates().get("safety_eval").io_contract
    assert contract_is_compatible(
        contract, required_inputs={"scenario": "object"}, required_outputs={}
    )
    assert not contract_is_compatible(
        contract, required_inputs={}, required_outputs={"artifact": "object"}
    )


def test_registry_search_compatible_delegates_to_port_search() -> None:
    registry = default_graph_templates()
    wanted = {"scenario": "object"}
    assert registry.search_compatible(wanted) == ["safety_eval"]
    assert registry.search_compatible(wanted) == search_compatible_recipes(registry, wanted)
    assert registry.search_compatible(required_outputs={"artifact": "object"}) == [
        "produce_critique_refine",
        "verify_repair",
    ]
