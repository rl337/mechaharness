"""Static tests for change_execution / gastronomic M6 increment 3."""

from __future__ import annotations

from pathlib import Path

from pyiv.files import MemoryFilesystem

from mechaharness.change_execution import (
    apply_file_revisions,
    assemble_change_execution,
    extract_execution_constraints,
    validate_change_execution,
)
from mechaharness.graph_templates import (
    ChangeExecutionTemplate,
    GastronomicGuidedDevelopmentTemplate,
    GraphTemplateParams,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for


def test_change_execution_in_default_catalog() -> None:
    names = default_graph_templates().names()
    assert "change_execution" in names


def test_change_execution_topology() -> None:
    template = ChangeExecutionTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Apply multiply helper",
            inputs={
                "goal": "Apply multiply helper",
                "approved_slice": {
                    "id": "arithmetic",
                    "scope": {"paths": ["src/calc/arithmetic.py"]},
                },
                "workspace": {"root": "."},
            },
        )
    )
    assert graph.template_name == "change_execution"
    assert sorted(graph.nodes) == [
        "apply",
        "constrain",
        "publish",
        "seed",
        "validate",
    ]
    comps = node_components_for(graph, template=template)
    soft = {c.soft_point_name for c in comps if c.kind == "soft_point"}
    assert "apply_payload" in soft


def test_gastronomic_tiles_execute_after_plan() -> None:
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
    assert "plan_tile" in graph.nodes
    assert "execute_tile" in graph.nodes
    assert "verify_tile" in graph.nodes
    assert "diagnose_tile" in graph.nodes
    assert graph.nodes["execute_tile"].subgraph
    assert graph.nodes["verify_tile"].subgraph
    assert graph.nodes["diagnose_tile"].subgraph


def test_apply_in_scope_publishes_diff_and_hashes() -> None:
    fs = MemoryFilesystem()
    root = Path("/workspace")
    before = "def add(a, b):\n    return a + b\n"
    after = "def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n"
    target = root / "src" / "calc" / "arithmetic.py"
    fs.mkdir(str(target.parent), parents=True)
    fs.write_text(str(target), before)

    constraints = extract_execution_constraints(
        approved_slice={
            "id": "arithmetic",
            "title": "Add multiply helper",
            "scope": {"paths": ["src/calc/arithmetic.py"]},
            "rollback": "revert arithmetic.py",
        }
    )
    assert constraints["status"] == "ok"
    receipt = apply_file_revisions(
        fs=fs,
        root=root,
        revisions=[{"path": "src/calc/arithmetic.py", "content": after}],
        allowed_paths=constraints["allowed_paths"],
    )
    assert receipt["status"] == "ok"
    assert receipt["written"][0]["sha256_before"]
    assert receipt["written"][0]["sha256_after"]
    assert receipt["written"][0]["sha256_before"] != receipt["written"][0]["sha256_after"]
    assert "mul" in receipt["written"][0]["diff"]
    result = assemble_change_execution(constraints=constraints, apply_receipt=receipt)
    assert result["status"] == "ok"
    assert result["slice_id"] == "arithmetic"
    assert result["changed_files"][0]["path"] == "src/calc/arithmetic.py"
    assert not result["scope_violations"]
    assert validate_change_execution(result)["ok"] is True


def test_apply_refuses_scope_escape() -> None:
    fs = MemoryFilesystem()
    root = Path("/workspace")
    fs.mkdir(str(root), parents=True)
    constraints = extract_execution_constraints(
        approved_slice={
            "id": "arithmetic",
            "scope": {"paths": ["src/calc/arithmetic.py"]},
        }
    )
    receipt = apply_file_revisions(
        fs=fs,
        root=root,
        revisions=[{"path": "secrets/token.txt", "content": "nope"}],
        allowed_paths=constraints["allowed_paths"],
    )
    assert receipt["status"] == "failed"
    assert receipt["refused"][0]["reason"] == "scope_escape"
    result = assemble_change_execution(constraints=constraints, apply_receipt=receipt)
    assert result["status"] == "failed"
    assert result["scope_violations"]
