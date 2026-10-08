"""Data-driven coverage for library graph templates (static models only)."""

from __future__ import annotations

import pytest
from pyiv import get_injector

from mechaharness.core.access import GraphExecute
from mechaharness.di import MechaHarnessConfig
from mechaharness.graph_templates import (
    FanOutAggregateTemplate,
    GraphTemplateParams,
    GraphTemplateRegistry,
    IndependentReviewTemplate,
    SoftPoint,
    default_graph_templates,
)
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.mock import MockInferenceStrategy
from tests.support.graph_templates_cases import (
    assert_expect,
    build_params,
    iter_cases,
)


class _TplConfig(MechaHarnessConfig):
    def get_inference_class(self):
        return MockInferenceStrategy

    def get_harness_class(self):
        return PassThroughHarness

    def get_grants(self):
        return [GraphExecute]


_CASES = iter_cases()


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.id)
def test_graph_template_fixtures(case) -> None:
    assert _CASES, "expected graph_templates fixtures"
    registry = default_graph_templates()
    template_name = str(case.data["template"])
    template = registry.get(template_name)
    assert template is not None, f"unknown template {template_name}"
    params = build_params(case.data.get("params"))
    graph = template.instantiate(params)
    assert_expect(graph=graph, expect=case.data["expect"], case_id=case.id)


def test_catalog_describes_soft_points() -> None:
    catalog = default_graph_templates().catalog()
    names = {row["name"] for row in catalog}
    assert names >= {
        "fan_out_aggregate",
        "verify_repair",
        "independent_review",
        "environment_repair",
    }
    for row in catalog:
        assert row["summary"]
        assert isinstance(row["soft_points"], list)
        assert row["soft_points"], f"{row['name']} must declare soft points"
        SoftPoint.model_validate(row["soft_points"][0])


def test_registry_bound_via_di() -> None:
    inj = get_injector(_TplConfig())
    registry = inj.inject(GraphTemplateRegistry)
    assert "fan_out_aggregate" in registry.names()


def test_fixture_matrix_nonempty_unique_ids() -> None:
    ids = [c.id for c in _CASES]
    assert len(ids) >= 4
    assert len(ids) == len(set(ids))


def test_demoted_template_refuses_instantiate() -> None:
    template = FanOutAggregateTemplate()
    template.status = "demoted"
    with pytest.raises(RuntimeError, match="demoted"):
        template.instantiate(GraphTemplateParams(goal="nope"))


def test_source_workflow_ref_stamped() -> None:
    graph = IndependentReviewTemplate().instantiate(
        GraphTemplateParams(
            goal="review",
            source_workflow_ref="client:workflows/review_v3",
        )
    )
    assert graph.source_workflow_ref == "client:workflows/review_v3"
    assert graph.template_name == "independent_review"

def test_instance_key_namespaces_and_is_deterministic() -> None:
    from mechaharness.graph_templates import VerifyRepairTemplate

    template = VerifyRepairTemplate()
    a = template.instantiate(GraphTemplateParams(goal="g", instance_key="a"))
    b = template.instantiate(GraphTemplateParams(goal="g", instance_key="a"))
    assert set(a.nodes) == set(b.nodes)
    assert a.recipe_params_fingerprint == b.recipe_params_fingerprint
    assert a.recipe_instance_id == "verify_repair/a"
    assert "verify_repair/a/produce" in a.nodes
    other = template.instantiate(GraphTemplateParams(goal="g", instance_key="b"))
    assert set(a.nodes).isdisjoint(other.nodes)


def test_tile_embeds_namespaced_child() -> None:
    from mechaharness.graph import ExecutionGraph
    from mechaharness.graph_templates import VerifyRepairTemplate

    template = VerifyRepairTemplate()
    child, embed = template.tile(
        GraphTemplateParams(goal="child", instance_key="left"),
        parent_node_id="embed_left",
    )
    parent = ExecutionGraph(goal="parent")
    parent.add_node(embed)
    assert embed.kind == "subgraph"
    assert child.recipe_instance_id == "verify_repair/left"
    assert embed.payload.get("recipe_instance_id") == child.recipe_instance_id


def test_catalog_marks_agentic_recipe_category() -> None:
    catalog = default_graph_templates().catalog()
    assert all(row.get("category") == "agentic_recipe" for row in catalog)

