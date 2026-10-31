"""Static tests for the workspace_discovery Agentic Recipe (gastronomic M5)."""

from __future__ import annotations

from mechaharness.discovery_hard_nodes import (
    publish_workspace_inventory,
    run_discovery_preflight,
)
from mechaharness.graph_templates import (
    GraphTemplateParams,
    WorkspaceDiscoveryTemplate,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for


def test_workspace_discovery_in_default_catalog() -> None:
    assert "workspace_discovery" in default_graph_templates().names()


def test_workspace_discovery_tiles_hard_and_soft_nodes() -> None:
    template = WorkspaceDiscoveryTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Find division-by-zero handling",
            inputs={
                "goal": "Find division-by-zero handling",
                "workspace": {"root": "."},
                "constraints": {"read_only": True, "max_files": 40},
            },
        )
    )
    assert graph.template_name == "workspace_discovery"
    assert graph.nodes["hypotheses"].kind == "infer"
    assert graph.nodes["interpret"].kind == "infer"
    assert graph.nodes["publish"].kind == "inventory_publish"
    assert graph.nodes["manifest"].payload["parameters"]["max_files"] == 40
    comps = node_components_for(graph, template=template)
    soft = {c.soft_point_name for c in comps if c.kind == "soft_point"}
    assert "hypotheses_payload" in soft
    assert "interpret_payload" in soft


def test_publish_workspace_inventory_status_matrix() -> None:
    manifest = {
        "files": [{"path": "a.py", "sha256": "abc"}],
        "coverage": {"file_count": 1, "truncated": False},
    }
    found = publish_workspace_inventory(
        goal="g",
        manifest=manifest,
        verified={
            "verified": [{"path": "a.py", "sha256": "abc", "start_line": 1, "end_line": 2}],
            "rejected": [],
        },
        coverage={"status": "sufficient", "truncated": False, "file_count": 1},
    )
    assert found["status"] == "found"
    assert found["relevant_files"][0]["path"] == "a.py"

    not_found = publish_workspace_inventory(
        goal="g",
        manifest=manifest,
        verified={"verified": [], "rejected": []},
        coverage={"status": "sufficient", "truncated": False, "file_count": 1},
    )
    assert not_found["status"] == "not_found"

    inconclusive = publish_workspace_inventory(
        goal="g",
        manifest=manifest,
        verified={"verified": [{"path": "a.py"}], "rejected": []},
        coverage={"status": "inconclusive", "truncated": True, "file_count": 1},
    )
    assert inconclusive["status"] == "inconclusive"

    failed = publish_workspace_inventory(
        goal="",
        manifest=manifest,
        verified={"verified": [], "rejected": []},
        coverage={"status": "sufficient", "file_count": 1},
        preflight={"ok": False, "errors": [{"path": "in.goal", "message": "required"}]},
    )
    assert failed["status"] == "failed"


def test_discovery_preflight_requires_read_only_goal_and_root() -> None:
    ok = run_discovery_preflight(
        goal="find x",
        workspace={"root": "."},
        constraints={"read_only": True},
    )
    assert ok["ok"] is True
    bad = run_discovery_preflight(goal="", workspace={}, constraints={"read_only": False})
    assert bad["ok"] is False
    paths = {e["path"] for e in bad["errors"]}
    assert "in.goal" in paths
    assert "in.workspace" in paths
    assert "in.constraints.read_only" in paths
