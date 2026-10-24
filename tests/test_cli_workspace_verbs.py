"""Unit tests for run_python / workspace_read verbs."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mechaharness.cli_workspace_verbs import (
    RunPythonParams,
    RunPythonVerb,
    WorkspaceReadParams,
    WorkspaceReadVerb,
)


class _Runtime:
    def __init__(self, root: Path) -> None:
        self.workspace_root = root


@pytest.mark.asyncio
async def test_run_python_code_stdout(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)
    out = await RunPythonVerb().run(
        RunPythonParams(code="print(2 + 3)"),
        runtime,
    )
    assert out["exit_code"] == 0
    assert "5" in out["stdout"]
    assert out["stderr"] == ""
    assert out["workspace_root"] == str(tmp_path.resolve())
    assert out["cmd"][0]


@pytest.mark.asyncio
async def test_run_python_path_script(tmp_path: Path) -> None:
    script = tmp_path / "hello.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    out = await RunPythonVerb().run(
        RunPythonParams(path="hello.py"),
        _Runtime(tmp_path),
    )
    assert out["exit_code"] == 0
    assert "hi" in out["stdout"]


@pytest.mark.asyncio
async def test_run_python_rejects_both_code_and_path() -> None:
    with pytest.raises(ValidationError):
        RunPythonParams(code="print(1)", path="x.py")


@pytest.mark.asyncio
async def test_workspace_read_exists_and_missing(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    runtime = _Runtime(tmp_path)
    found = await WorkspaceReadVerb().run(
        WorkspaceReadParams(path="a.txt"),
        runtime,
    )
    assert found["exists"] is True
    assert found["text"] == "hello\n"
    missing = await WorkspaceReadVerb().run(
        WorkspaceReadParams(path="nope.txt"),
        runtime,
    )
    assert missing["exists"] is False
    assert missing["text"] is None


@pytest.mark.asyncio
async def test_workspace_read_rejects_escape(tmp_path: Path) -> None:
    out = await WorkspaceReadVerb().run(
        WorkspaceReadParams(path="../outside.txt"),
        _Runtime(tmp_path),
    )
    assert out["exists"] is False
    assert out.get("error")
