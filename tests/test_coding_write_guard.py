"""Regression: Completer gutting large files must be refused at write_file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from pyiv.files import RealFilesystem

from mechaharness.coding_write_guard import CodingWriteGuard, DEFAULT_CODING_WRITE_GUARD
from mechaharness.project_coding_tools import WorkspacePaths, build_coding_tool_registry


# Representative "healthy" module (≥512 bytes; mirrors pre-gutting tools modules).
_HEALTHY_MODULE = (
    '''\
"""Workspace coding tools (healthy baseline for gutting regression)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkspacePaths:
    """Resolve paths under a workspace root."""

    root: str

    def resolve(self, relative: str) -> str:
        return f"{self.root}/{relative}"


def build_coding_tool_registry(*, workspace: WorkspacePaths) -> dict[str, object]:
    """Register confined tools under *workspace*."""

    def read_file(path: str) -> str:
        return f"read:{path}"

    def write_file(path: str, content: str) -> str:
        return f"wrote:{path}:{len(content)}"

    return {"read_file": read_file, "write_file": write_file, "paths": workspace}


def helper() -> int:
    return 42
'''
    + ("\n# padding to exceed CodingWriteGuard.min_existing_bytes\n" * 12)
)

# What the failing local Completer actually wrote (tiny stub).
_GUTTED_STUB = '''\
from mechaharness.github_client import GitHubClient

def ci_checks(github_client: GitHubClient, repo: str, workflow_id: int):
    return github_client.list_check_runs(repo, workflow_id)

def build_coding_tool_registry(github_client=None):
    return {"ci_checks": ci_checks if github_client else None}
'''


@dataclass(frozen=True)
class _GuardCase:
    id: str
    existing: str | None
    new: str
    expect_refuse: bool
    needle: str | None = None


_GUARD_CASES = [
    _GuardCase(
        id="allow_new_file",
        existing=None,
        new="def ok() -> int:\n    return 1\n",
        expect_refuse=False,
    ),
    _GuardCase(
        id="allow_modest_edit",
        existing=_HEALTHY_MODULE,
        new=_HEALTHY_MODULE + "\n# note\n",
        expect_refuse=False,
    ),
    _GuardCase(
        id="refuse_byte_gutting",
        existing=_HEALTHY_MODULE,
        new=_GUTTED_STUB,
        expect_refuse=True,
        needle="file gutting",
    ),
    _GuardCase(
        id="refuse_syntax_break",
        existing=_HEALTHY_MODULE,
        new=_HEALTHY_MODULE[: len(_HEALTHY_MODULE) // 2] + "\ndef broken(\n",
        expect_refuse=True,
        needle="syntax error",
    ),
    _GuardCase(
        id="refuse_drop_all_defs",
        existing=_HEALTHY_MODULE,
        # Large enough to pass size ratio, but no retained defs/classes.
        new=("# wiped\n" + ("x = 1\n" * 400)),
        expect_refuse=True,
        needle="dropped all prior",
    ),
]


@pytest.mark.parametrize("case", _GUARD_CASES, ids=lambda c: c.id)
def test_coding_write_guard_cases(case: _GuardCase) -> None:
    err = DEFAULT_CODING_WRITE_GUARD.check(
        path="tools.py", existing=case.existing, new_content=case.new
    )
    if case.expect_refuse:
        assert err is not None
        if case.needle:
            assert case.needle in err.lower() or case.needle in err
    else:
        assert err is None


def test_write_file_tool_refuses_gutting_and_preserves_bytes(tmp_path: Path) -> None:
    """Reproduce the MCP Completer gutting incident through write_file."""
    root = tmp_path
    target = root / "project_coding_tools.py"
    target.write_text(_HEALTHY_MODULE, encoding="utf-8")
    before = target.read_text(encoding="utf-8")
    assert len(before.encode("utf-8")) >= 512

    tools = build_coding_tool_registry(
        workspace=WorkspacePaths(root),
        filesystem=RealFilesystem(),
    )
    write = tools.get("write_file")
    assert write is not None
    result = write.handler(path="project_coding_tools.py", content=_GUTTED_STUB)
    assert '"ok": false' in result.lower() or '"ok":false' in result.replace(" ", "").lower()
    assert "gutting" in result.lower()
    after = target.read_text(encoding="utf-8")
    assert after == before
    assert "build_coding_tool_registry" in after
    assert "WorkspacePaths" in after


def test_write_file_tool_allows_legitimate_growth(tmp_path: Path) -> None:
    root = tmp_path
    (root / "mod.py").write_text(_HEALTHY_MODULE, encoding="utf-8")
    tools = build_coding_tool_registry(
        workspace=WorkspacePaths(root),
        filesystem=RealFilesystem(),
    )
    write = tools.get("write_file")
    assert write is not None
    expanded = _HEALTHY_MODULE + "\n\ndef extra() -> str:\n    return 'ok'\n"
    result = write.handler(path="mod.py", content=expanded)
    assert result.startswith("wrote ")
    assert "extra" in (root / "mod.py").read_text(encoding="utf-8")


def test_custom_guard_can_be_stricter(tmp_path: Path) -> None:
    root = tmp_path
    (root / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    tools = build_coding_tool_registry(
        workspace=WorkspacePaths(root),
        filesystem=RealFilesystem(),
        write_guard=CodingWriteGuard(
            min_existing_bytes=1,
            min_retain_ratio=0.99,
            min_replacement_bytes=1,
            require_retain_some_defs=False,
        ),
    )
    write = tools.get("write_file")
    assert write is not None
    # Slightly shorter replacement of a tiny file → refuse under 99% retain.
    result = write.handler(path="a.py", content="def a():\n return 1\n")
    assert "gutting" in result.lower() or "refused" in result.lower()
