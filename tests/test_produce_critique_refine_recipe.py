"""produce_critique_refine recipe: structure, soft points, node components."""

from __future__ import annotations

import pytest

from mechaharness.graph_templates import (
    GraphTemplateParams,
    ProduceCritiqueRefineTemplate,
    default_graph_templates,
)
from mechaharness.node_component import NODE_COMPONENT_KINDS, node_components_for
from mechaharness.stop_contract import StopContract

_BINDINGS = [
    ("default_rounds", {}, None, 2),
    ("bound_rounds", {"max_rounds": 4}, None, 4),
    ("explicit_stop_wins", {"max_rounds": 4}, StopContract(version="1", max_iterations=1), 1),
]


@pytest.mark.parametrize(
    ("case_id", "bindings", "stop", "rounds"), _BINDINGS, ids=[c[0] for c in _BINDINGS]
)
def test_refine_rounds_come_from_soft_point_or_stop_contract(
    case_id: str, bindings: dict, stop: StopContract | None, rounds: int
) -> None:
    del case_id
    graph = ProduceCritiqueRefineTemplate().instantiate(
        GraphTemplateParams(goal="g", soft_bindings=bindings, stop_contract=stop)
    )
    assert graph.nodes["refine"].repeating is True
    assert graph.nodes["refine"].stop_contract["max_iterations"] == rounds


def test_critic_isolation_can_be_relaxed_by_the_host() -> None:
    graph = ProduceCritiqueRefineTemplate().instantiate(
        GraphTemplateParams(goal="g", soft_bindings={"omit_producer_reasoning": False})
    )
    assert graph.nodes["critique"].payload["omit_producer_reasoning"] is False
    assert graph.nodes["critique"].payload["isolated_context"] is True


def test_instance_key_namespaces_ids() -> None:
    graph = ProduceCritiqueRefineTemplate().instantiate(
        GraphTemplateParams(goal="g", instance_key="notes")
    )
    assert "produce_critique_refine/notes/critique" in graph.nodes
    assert graph.recipe_instance_id == "produce_critique_refine/notes"


def test_node_components_cover_every_soft_point_and_the_stop_contract() -> None:
    template = ProduceCritiqueRefineTemplate()
    graph = template.instantiate(GraphTemplateParams(goal="g"))
    comps = node_components_for(graph, template=template)
    assert all(c.kind in NODE_COMPONENT_KINDS and c.parent_node_id in graph.nodes for c in comps)
    by_parent: dict[str, set[str]] = {}
    for comp in comps:
        by_parent.setdefault(comp.parent_node_id, set()).add(comp.soft_point_name or comp.kind)
    assert by_parent == {
        "produce": {"produce_kind"},
        "critique": {"critique_kind", "critique_prompt", "omit_producer_reasoning", "acceptance"},
        "refine": {"stop_contract", "refine_kind", "max_rounds"},
        "complete": {"complete_kind"},
    }
    declared = {sp.name for sp in template.soft_points}
    assert declared == {n for names in by_parent.values() for n in names} - {"stop_contract"}


def test_registered_in_default_catalog_with_pydoc_example() -> None:
    row = next(
        r for r in default_graph_templates().catalog() if r["name"] == "produce_critique_refine"
    )
    assert "Example" in row["doc"]
    assert {p["name"]: p["evolvable"] for p in row["soft_points"]}["max_rounds"] is True
