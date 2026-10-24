"""Unit tests for audited_decision domain + audited_infer_accept recipe."""

from __future__ import annotations

import pytest

from mechaharness.audited_decision import (
    STAGES,
    AuditedDecisionError,
    AuditedDecisionSpec,
    assert_principals_distinct,
    criteria_hash,
    repair_target,
)
from mechaharness.graph import GraphNode
from mechaharness.graph_templates import (
    AuditedInferAcceptTemplate,
    GraphTemplateParams,
    default_graph_templates,
)
from mechaharness.graph_templates.audited_infer_accept import append_audited_infer_accept


def test_stages_order() -> None:
    assert STAGES == (
        "collect",
        "freeze_criteria",
        "decide",
        "independent_qa",
        "deterministic",
        "gate",
    )


def test_criteria_hash_stable() -> None:
    assert criteria_hash(["a", "b"]) == criteria_hash(["a", "b"])
    assert criteria_hash(["a", "b"]) != criteria_hash(["b", "a"])


def test_principals_must_differ() -> None:
    assert_principals_distinct("a", "b")
    with pytest.raises(AuditedDecisionError):
        assert_principals_distinct("same", "same")
    with pytest.raises(AuditedDecisionError):
        assert_principals_distinct("", "qa")


def test_repair_target_mapping() -> None:
    assert repair_target("missing_evidence") == "collect"
    assert repair_target("weak_criteria") == "freeze_criteria"
    assert repair_target("qa_fail") == "decide"
    with pytest.raises(AuditedDecisionError):
        repair_target("unknown_defect")


def test_audited_decision_spec_frozen_bundle() -> None:
    spec = AuditedDecisionSpec(
        task_id="t1",
        modality="text",
        acceptance_criteria=("ok",),
        hop="hop-1",
    )
    bundle = spec.frozen_bundle()
    assert bundle["criteria_hash"]
    assert bundle["decide_principal"] != bundle["qa_principal"]


def test_audited_infer_accept_in_catalog() -> None:
    assert "audited_infer_accept" in default_graph_templates().names()


def test_audited_infer_accept_simple_spine() -> None:
    graph = AuditedInferAcceptTemplate().instantiate(
        GraphTemplateParams(
            goal="demo",
            soft_bindings={
                "task_id": "demo",
                "simple_ids": True,
                "acceptance_criteria": ["done"],
            },
            inputs={"simple_ids": True, "task_id": "demo"},
        )
    )
    assert graph.template_name == "audited_infer_accept"
    for stage in ("collect", "freeze", "decide", "qa", "deterministic", "gate"):
        assert stage in graph.nodes
    assert graph.nodes["decide"].kind == "audited.text.decide"
    assert graph.nodes["qa"].kind == "audited.text.qa"


def test_append_audited_infer_accept_image_kinds() -> None:
    nodes: list[GraphNode] = []
    gate = append_audited_infer_accept(
        nodes,
        after=None,
        task_id="img-1",
        modality="image",
        simple_ids=True,
        base={"acceptance_criteria": ["pixels_ok"]},
    )
    assert gate == "gate"
    kinds = {n.id: n.kind for n in nodes}
    assert kinds["decide"] == "audited.image.decide"
    assert kinds["qa"] == "audited.image.qa"
