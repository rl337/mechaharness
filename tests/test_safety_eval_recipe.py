"""safety_eval recipe: structure, soft points, node components (MH-DOTS-08)."""

from __future__ import annotations

from mechaharness.graph_templates import (
    GraphTemplateParams,
    SafetyEvalTemplate,
    default_graph_templates,
)
from mechaharness.graph_templates.safety_eval import (
    SAFETY_REPORT_FIELDS,
    SAFETY_SCENARIO_CLASSES,
)
from mechaharness.node_component import NODE_COMPONENT_KINDS, node_components_for


def test_topology_isolation_and_report_fields() -> None:
    graph = SafetyEvalTemplate().instantiate(
        GraphTemplateParams(goal="g", inputs={"model_version": "m-1"}, acceptance=["safe"])
    )
    assert list(graph.nodes) == ["produce", "review", "score"]
    assert graph.nodes["review"].depends_on == ["produce"]
    assert graph.nodes["review"].payload["isolated_context"] is True
    assert graph.nodes["review"].payload["omit_producer_reasoning"] is True
    score = graph.nodes["score"].payload
    assert score["deterministic"] is True
    assert score["report_fields"] == list(SAFETY_REPORT_FIELDS)
    assert score["model_version"] == "m-1" and score["recipe_version"] == "1"
    assert graph.nodes["produce"].payload["scenario_classes"] == list(SAFETY_SCENARIO_CLASSES)


def test_scenario_classes_cover_the_inspiration_fixture_pack() -> None:
    assert set(SAFETY_SCENARIO_CLASSES) == {
        "prompt_injection_in_tool_output",
        "scope_bleed",
        "authorization_change",
        "ambiguous_consent",
        "warning_disregard",
        "false_denial_control",
    }


def test_scenario_classes_are_a_soft_binding() -> None:
    graph = SafetyEvalTemplate().instantiate(
        GraphTemplateParams(goal="g", soft_bindings={"scenario_classes": ["scope_bleed"]})
    )
    assert graph.nodes["produce"].payload["scenario_classes"] == ["scope_bleed"]


def test_nothing_is_evolvable_so_an_optimizer_cannot_tune_the_instrument() -> None:
    assert SafetyEvalTemplate().evolvable_soft_point_names() == []


def test_node_components_cover_every_soft_point() -> None:
    template = SafetyEvalTemplate()
    graph = template.instantiate(GraphTemplateParams(goal="g"))
    comps = node_components_for(graph, template=template)
    assert all(c.kind in NODE_COMPONENT_KINDS and c.parent_node_id in graph.nodes for c in comps)
    by_parent: dict[str, set[str]] = {}
    for comp in comps:
        by_parent.setdefault(comp.parent_node_id, set()).add(comp.soft_point_name or comp.kind)
    assert by_parent == {
        "produce": {"produce_kind", "scenario_classes"},
        "review": {"review_kind", "review_prompt", "omit_producer_reasoning"},
        "score": {"score_kind", "severity_scale"},
    }


def test_registered_with_ports_and_pydoc_example() -> None:
    registry = default_graph_templates()
    row = next(r for r in registry.catalog() if r["name"] == "safety_eval")
    assert "Example" in row["doc"]
    assert registry.get("safety_eval").io_contract.outputs == {"safety_report": "object"}
