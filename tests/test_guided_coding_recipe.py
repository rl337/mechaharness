"""Static tests for the guided_coding Agentic Recipe topology."""

from __future__ import annotations

from mechaharness.graph_templates import (
    GraphTemplateParams,
    GuidedCodingTemplate,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for


def test_guided_coding_in_default_catalog() -> None:
    assert "guided_coding" in default_graph_templates().names()


def test_guided_coding_tiles_code_and_audit() -> None:
    graph = GuidedCodingTemplate().instantiate(
        GraphTemplateParams(goal="ship helper")
    )
    assert graph.template_name == "guided_coding"
    assert "brief" in graph.nodes
    assert "code_loop" in graph.nodes
    assert "audit_tile" in graph.nodes
    assert "verify_tile" not in graph.nodes
    assert graph.nodes["code_loop"].subgraph
    assert graph.nodes["audit_tile"].subgraph
    # Nested audited spine uses aa_* prefixed ids under the tile subgraph.
    child = graph.nodes["audit_tile"].subgraph
    assert isinstance(child, dict)
    child_nodes = child.get("nodes") or {}
    assert any("collect" in str(nid) or "decide" in str(nid) for nid in child_nodes)
    comps = node_components_for(graph)
    kinds = {c.kind for c in comps}
    assert "soft_point" in kinds or "guidance_request" in kinds or "child_graph" in kinds
