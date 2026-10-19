"""GraphTemplateRegistry versions, active pointer, and evolvable soft points (MH-SR-01/03/05)."""

from __future__ import annotations

import pytest

from mechaharness.graph_templates import (
    GraphTemplateRegistry,
    IndependentReviewTemplate,
    ProduceCritiqueRefineTemplate,
    SoftPoint,
    VerifyRepairTemplate,
    default_graph_templates,
)


class _V2(VerifyRepairTemplate):
    version = "2"


class _V3(VerifyRepairTemplate):
    version = "3"


def _registry() -> GraphTemplateRegistry:
    return GraphTemplateRegistry([VerifyRepairTemplate()])


def test_register_stays_replace_by_name_and_activates() -> None:
    reg = _registry()
    reg.register(_V2())
    assert reg.get("verify_repair").version == "2"
    assert reg.versions("verify_repair") == ["1", "2"]
    assert reg.names() == ["verify_repair"]


def test_add_version_is_inactive_until_promoted() -> None:
    reg = _registry()
    reg.add_version(_V2())
    assert reg.active_version("verify_repair") == "1"
    assert reg.get("verify_repair", version="2").version == "2"
    reg.promote("verify_repair", "2")
    assert reg.active_version("verify_repair") == "2"
    assert reg.get("verify_repair").version == "2"


def test_rollback_walks_pointer_history_back() -> None:
    reg = _registry()
    reg.add_version(_V2())
    reg.add_version(_V3())
    reg.promote("verify_repair", "2")
    reg.promote("verify_repair", "3")
    assert reg.rollback("verify_repair") == "2"
    assert reg.rollback("verify_repair") == "1"
    with pytest.raises(ValueError, match="no previous version"):
        reg.rollback("verify_repair")
    # Old versions stay immutable artifacts after rollback.
    assert reg.versions("verify_repair") == ["1", "2", "3"]


def test_versions_are_immutable_and_promote_needs_a_stored_version() -> None:
    reg = _registry()
    reg.add_version(_V2())
    with pytest.raises(ValueError, match="immutable"):
        reg.add_version(_V2())  # different object, same name+version
    with pytest.raises(KeyError):
        reg.promote("verify_repair", "9")
    with pytest.raises(KeyError):
        reg.promote("missing", "1")


def test_merge_carries_versions_and_active_pointer() -> None:
    other = _registry()
    other.add_version(_V2())
    other.promote("verify_repair", "2")
    merged = GraphTemplateRegistry([]).merge(other)
    assert merged.versions("verify_repair") == ["1", "2"]
    assert merged.active_version("verify_repair") == "2"
    assert merged.get("verify_repair", version="1").version == "1"


def test_unknown_names_and_versions_return_none() -> None:
    reg = _registry()
    assert reg.get("nope") is None
    assert reg.get("verify_repair", version="9") is None


def test_active_names_follow_the_active_version_status() -> None:
    class _Demoted(VerifyRepairTemplate):
        version = "2"
        status = "demoted"

    reg = _registry()
    reg.add_version(_Demoted())
    assert reg.active_names() == ["verify_repair"]
    reg.promote("verify_repair", "2")
    assert reg.active_names() == []


def test_soft_point_evolvable_defaults_false() -> None:
    assert SoftPoint(name="x").evolvable is False


def test_evolvable_allowlist_gates_optimizer_edits() -> None:
    template = ProduceCritiqueRefineTemplate()
    assert template.evolvable_soft_point_names() == ["critique_prompt", "max_rounds"]
    template.assert_evolution_allowed(["critique_prompt"])
    with pytest.raises(ValueError, match="omit_producer_reasoning"):
        template.assert_evolution_allowed(["max_rounds", "omit_producer_reasoning"])
    assert IndependentReviewTemplate().evolvable_soft_point_names() == ["reviewer_count"]
    assert VerifyRepairTemplate().evolvable_soft_point_names() == []
    with pytest.raises(ValueError):
        VerifyRepairTemplate().assert_evolution_allowed(["produce_kind"])


def test_default_catalog_includes_new_recipe_and_versions() -> None:
    reg = default_graph_templates()
    assert "produce_critique_refine" in reg.names()
    assert reg.versions("produce_critique_refine") == ["1"]


def test_lineage_records_parents_and_evaluations_attach_to_versions() -> None:
    reg = _registry()
    reg.add_version(_V2(), parent_version="1")
    reg.add_version(_V3(), parent_version="2")
    assert reg.lineage("verify_repair") == {"1": None, "2": "1", "3": "2"}
    with pytest.raises(KeyError):
        reg.add_version(type("V9", (VerifyRepairTemplate,), {"version": "9"})(), parent_version="8")
    reg.attach_evaluation("verify_repair", "2", {"pass_rate": 0.9})
    reg.attach_evaluation("verify_repair", "2", {"pass_rate": 0.95})
    assert [r["pass_rate"] for r in reg.evaluations("verify_repair", "2")] == [0.9, 0.95]
    assert reg.evaluations("verify_repair", "3") == []
    with pytest.raises(KeyError):
        reg.attach_evaluation("verify_repair", "9", {})
    merged = GraphTemplateRegistry([]).merge(reg)
    assert merged.lineage("verify_repair") == reg.lineage("verify_repair")
    assert merged.evaluations("verify_repair", "2") == reg.evaluations("verify_repair", "2")


def _container(*, free_form: bool = False, unregistered: bool = False):  # type: ignore[no-untyped-def]
    from mechaharness.graph import ExecutionGraph, GraphNode
    from mechaharness.graph_templates import GraphTemplateParams

    template = VerifyRepairTemplate()
    child, embed = template.tile(GraphTemplateParams(goal="g"), parent_node_id="verify_step")
    if unregistered:
        child.template_version = "99"
        embed = embed.model_copy(update={"subgraph": child.checkpoint()})
    parent = ExecutionGraph(goal="compose")
    parent.add_node(embed)
    if free_form:
        parent.add_node(GraphNode(id="adhoc", kind="shell"))
    return parent


_COMPOSITION_CASES = [
    ("pure_tiling_ok", {}, []),
    ("free_form_node", {"free_form": True}, ["free_form_node:adhoc"]),
    ("unregistered_version", {"unregistered": True}, ["unregistered_recipe:verify_repair@99"]),
]


@pytest.mark.parametrize(
    ("case_id", "kwargs", "issues"), _COMPOSITION_CASES, ids=[c[0] for c in _COMPOSITION_CASES]
)
def test_registry_only_composition(case_id: str, kwargs: dict, issues: list[str]) -> None:
    del case_id
    reg = _registry()
    graph = _container(**kwargs)
    assert reg.composition_violations(graph) == issues
    if issues:
        with pytest.raises(ValueError, match="not registry-composed"):
            reg.assert_registry_composed(graph)
    else:
        reg.assert_registry_composed(graph)


def test_stamped_recipe_graph_is_registry_composed_and_hand_graph_is_not() -> None:
    from mechaharness.graph import ExecutionGraph, GraphNode
    from mechaharness.graph_templates import GraphTemplateParams

    reg = _registry()
    stamped = VerifyRepairTemplate().instantiate(GraphTemplateParams(goal="g"))
    assert reg.composition_violations(stamped) == []
    hand = ExecutionGraph(goal="g")
    hand.add_node(GraphNode(id="x", kind="k"))
    assert reg.composition_violations(hand) == ["free_form_node:x"]
