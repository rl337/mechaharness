"""P0 discovery hard-node capabilities (gastronomic M4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from pyiv.files import MemoryFilesystem

from mechaharness.budget import Budget, BudgetPolicy
from mechaharness.discovery_hard_nodes import (
    DiscoveryHardNodeError,
    DiscoveryHardNodeRunner,
    build_workspace_manifest,
    extract_source_spans,
    measure_discovery_coverage,
    resolve_evidence_refs,
    search_manifest_files,
)
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import GraphRunContext
from mechaharness.walk_bag import WalkBag, WalkBagPathError


def _ctx(bag: WalkBag) -> GraphRunContext:
    return GraphRunContext(
        graph=ExecutionGraph(goal="t"),
        run_id="r",
        agent_id="a",
        budget=Budget(BudgetPolicy.unlimited()),
        bag=bag,
    )


def _fs_with_calc() -> tuple[MemoryFilesystem, Path]:
    fs = MemoryFilesystem()
    root = Path("/workspace")
    fs.mkdir(str(root), parents=True)
    fs.write_text(str(root / "calc.py"), "def add(a, b):\n    return a + b\n")
    fs.write_text(str(root / "README.md"), "calculator\n")
    fs.mkdir(str(root / ".git"), parents=True)
    fs.write_text(str(root / ".git" / "config"), "secret\n")
    return fs, root


@dataclass(frozen=True)
class ProjectCase:
    fields: tuple[str, ...]
    expect_keys: tuple[str, ...]
    expect_error: bool = False


@pytest.mark.parametrize(
    "case",
    [
        ProjectCase(("status", "files"), ("status", "files")),
        ProjectCase(("status", "missing"), (), expect_error=True),
    ],
    ids=["ok", "missing_field"],
)
@pytest.mark.asyncio
async def test_bag_project_cases(case: ProjectCase) -> None:
    bag = WalkBag()
    bag.path_put("out.discovery", {"status": "found", "files": ["calc.py"], "noise": 1})
    runner = DiscoveryHardNodeRunner(["bag_project"], filesystem=MemoryFilesystem())
    node = GraphNode(
        id="p",
        kind="bag_project",
        payload={
            "reads": {"source": "out.discovery"},
            "writes": {"destination": "ctx.summary"},
            "parameters": {"fields": list(case.fields)},
        },
    )
    outcome = await runner.run(node, context=_ctx(bag))
    if case.expect_error:
        assert outcome.status is NodeStatus.FAILED
        with pytest.raises(WalkBagPathError):
            bag.path_get("ctx.summary")
    else:
        assert outcome.status is NodeStatus.SUCCEEDED
        summary = bag.path_get("ctx.summary")
        assert set(summary) == set(case.expect_keys)
        assert "noise" not in summary


@pytest.mark.asyncio
async def test_bag_validate_report_and_fail_policy() -> None:
    bag = WalkBag()
    bag.path_put("out.discovery", {"status": "found"})
    runner = DiscoveryHardNodeRunner(["bag_validate"], filesystem=MemoryFilesystem())
    ctx = _ctx(bag)
    ok = await runner.run(
        GraphNode(
            id="v",
            kind="bag_validate",
            payload={
                "reads": {"source": "out.discovery"},
                "writes": {"destination": "acc.validation.discovery"},
                "parameters": {"required_fields": ["status", "files"]},
            },
        ),
        context=ctx,
    )
    assert ok.status is NodeStatus.SUCCEEDED
    report = bag.path_get("acc.validation.discovery")
    assert report["ok"] is False
    assert report["errors"]

    fail = await runner.run(
        GraphNode(
            id="v2",
            kind="bag_validate",
            payload={
                "reads": {"source": "out.discovery"},
                "writes": {"destination": "acc.validation.discovery2"},
                "parameters": {
                    "required_fields": ["status", "files"],
                    "fail_if_invalid": True,
                },
                "on_error": {"destination": "err.validate", "policy": "fail"},
            },
        ),
        context=ctx,
    )
    assert fail.status is NodeStatus.FAILED
    assert bag.path_get("err.validate")["ok"] is False


def test_workspace_manifest_excludes_and_hashes() -> None:
    fs, root = _fs_with_calc()
    manifest = build_workspace_manifest(fs=fs, root=root, max_files=10)
    paths = {row["path"] for row in manifest["files"]}
    assert paths == {"README.md", "calc.py"}
    assert all(row["sha256"] for row in manifest["files"])
    assert any(o["path"].startswith(".git") for o in manifest["omissions"])


def test_file_search_happy_and_typed_failures() -> None:
    fs, root = _fs_with_calc()
    manifest = build_workspace_manifest(fs=fs, root=root)
    found = search_manifest_files(
        fs=fs,
        root=root,
        manifest=manifest,
        queries=[{"id": "q1", "pattern": "def add", "mode": "literal"}],
    )
    assert found["matches"]
    assert found["matches"][0]["path"] == "calc.py"

    stale_files = [
        {**row, "sha256": "0" * 64} if row["path"] == "calc.py" else row
        for row in manifest["files"]
    ]
    stale = search_manifest_files(
        fs=fs,
        root=root,
        manifest={**manifest, "files": stale_files},
        queries=["def add"],
    )
    assert not stale["matches"]
    assert any(e["reason"] == "stale_hash" for e in stale["errors"])

    bad_rx = search_manifest_files(
        fs=fs,
        root=root,
        manifest=manifest,
        queries=[{"id": "bad", "pattern": "(", "mode": "regex"}],
    )
    assert not bad_rx["matches"]
    assert any(
        str(e.get("reason", "")).startswith("invalid_regex") for e in bad_rx["errors"]
    )


def test_source_extract_happy_and_typed_rejects() -> None:
    fs, root = _fs_with_calc()
    manifest = build_workspace_manifest(fs=fs, root=root)
    extracted = extract_source_spans(
        fs=fs,
        root=root,
        manifest=manifest,
        requests=[{"path": "calc.py", "start_line": 1, "end_line": 2}],
    )
    assert extracted["excerpts"]
    assert "def add" in extracted["excerpts"][0]["text"]

    rejected = extract_source_spans(
        fs=fs,
        root=root,
        manifest=manifest,
        requests=[
            {"path": "nope.py", "start_line": 1, "end_line": 1},
            {"path": "calc.py", "start_line": 99, "end_line": 100},
            {"path": "calc.py", "start_line": 1, "end_line": 500},
        ],
        max_lines=80,
    )
    reasons = {str(row["reason"]) for row in rejected["rejected"]}
    assert "not_in_manifest" in reasons
    assert "out_of_bounds" in reasons
    assert "span_too_large" in reasons
    assert not rejected["excerpts"]


def test_evidence_resolve_rejects_unknown_and_unverified_span() -> None:
    fs, root = _fs_with_calc()
    manifest = build_workspace_manifest(fs=fs, root=root)
    resolved = resolve_evidence_refs(
        proposals={"files": ["calc.py", "missing.py"]},
        manifest=manifest,
    )
    assert [v["path"] for v in resolved["verified"]] == ["calc.py"]
    assert any(r["reason"] == "unknown_path" for r in resolved["rejected"])
    assert resolved["ok"] is False

    span_reject = resolve_evidence_refs(
        proposals=[
            {"path": "calc.py", "start_line": 1, "end_line": 2},
        ],
        manifest=manifest,
        excerpts=[],  # require excerpt membership when spans are proposed
    )
    assert any(r["reason"] == "unverified_span" for r in span_reject["rejected"])


@dataclass(frozen=True)
class CoverageCase:
    truncated: bool
    min_files: int
    file_count: int
    expect: str


@pytest.mark.parametrize(
    "case",
    [
        CoverageCase(False, 1, 2, "sufficient"),
        CoverageCase(True, 1, 1, "inconclusive"),
        CoverageCase(False, 5, 1, "insufficient"),
    ],
    ids=["sufficient", "inconclusive_truncated", "insufficient_count"],
)
def test_coverage_measure_statuses(case: CoverageCase) -> None:
    report = measure_discovery_coverage(
        manifest={
            "files": [{"path": f"f{i}.py"} for i in range(case.file_count)],
            "omissions": [],
            "coverage": {
                "file_count": case.file_count,
                "truncated": case.truncated,
            },
        },
        search={"coverage": {"match_count": 0, "truncated": False}},
        min_files_scanned=case.min_files,
    )
    assert report["status"] == case.expect


def test_workspace_manifest_truncation() -> None:
    fs, root = _fs_with_calc()
    limited = build_workspace_manifest(fs=fs, root=root, max_files=1)
    assert limited["coverage"]["truncated"] is True
    assert limited["coverage"]["file_count"] == 1


@pytest.mark.asyncio
async def test_hard_node_atomic_no_partial_write_on_error() -> None:
    bag = WalkBag()
    bag.path_put("sentinel", "keep")
    runner = DiscoveryHardNodeRunner(["bag_project"], filesystem=MemoryFilesystem())
    outcome = await runner.run(
        GraphNode(
            id="p",
            kind="bag_project",
            payload={
                "reads": {"source": "missing.path"},
                "writes": {"destination": "ctx.summary"},
                "parameters": {"fields": ["x"]},
            },
        ),
        context=_ctx(bag),
    )
    assert outcome.status is NodeStatus.FAILED
    assert bag.path_get("sentinel") == "keep"
    with pytest.raises(WalkBagPathError):
        bag.path_get("ctx.summary")


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValueError, match="unknown"):
        DiscoveryHardNodeRunner(["not_a_real_kind"])


def test_discovery_hard_node_error_str() -> None:
    err = DiscoveryHardNodeError("boom")
    assert "boom" in str(err)
