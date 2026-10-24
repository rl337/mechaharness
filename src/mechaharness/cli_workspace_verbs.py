"""Workspace verify verbs: ``run_python`` and ``workspace_read``.

Product surface for user_story walks that inspect on-disk artifacts or
process stdout/stderr/exit_code. Results land in the step observation bag
for ordinary expect kinds (no side-effectful assertions).
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.cli_verb import CliVerb
from mechaharness.project_coding_tools import WorkspacePaths, resolve_workspace_root

_DEFAULT_TIMEOUT_SECONDS = 30.0


class RunPythonParams(BaseModel):
    """Run ``sys.executable`` under the session workspace."""

    model_config = ConfigDict(extra="forbid")

    code: str | None = None
    path: str | None = None
    args: list[str] = Field(default_factory=list)
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    @model_validator(mode="after")
    def _one_of_code_or_path(self) -> RunPythonParams:
        has_code = bool(self.code and self.code.strip())
        has_path = bool(self.path and str(self.path).strip())
        if has_code == has_path:
            raise ValueError("run_python requires exactly one of code or path")
        return self


class WorkspaceReadParams(BaseModel):
    """Read a workspace-relative path into the observation bag."""

    model_config = ConfigDict(extra="forbid")

    path: str


def _workspace_from_runtime(runtime: Any) -> WorkspacePaths:
    root = getattr(runtime, "workspace_root", None)
    if root is None:
        root = resolve_workspace_root(None)
    return WorkspacePaths(root)


class RunPythonVerb(CliVerb):
    """Execute Python in the workspace; expose stdout/stderr/exit_code."""

    name = "run_python"
    params_model = RunPythonParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = params if isinstance(params, RunPythonParams) else RunPythonParams.model_validate(
            params.model_dump() if isinstance(params, BaseModel) else params
        )
        paths = _workspace_from_runtime(runtime)
        if body.code is not None and body.code.strip():
            cmd: list[str] = [sys.executable, "-c", body.code, *list(body.args)]
        else:
            assert body.path is not None
            script = paths.resolve(body.path)
            cmd = [sys.executable, str(script), *list(body.args)]
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(paths.root),
                capture_output=True,
                text=True,
                timeout=float(body.timeout_seconds),
                check=False,
            )
            return {
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "exit_code": int(completed.returncode),
                "workspace_root": str(paths.root),
                "cmd": cmd,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "") if isinstance(exc.stderr, str) else (
                    str(exc.stderr or "") or f"timeout after {body.timeout_seconds}s"
                ),
                "exit_code": 124,
                "workspace_root": str(paths.root),
                "cmd": cmd,
                "error": "timeout",
            }


class WorkspaceReadVerb(CliVerb):
    """Stat/read a workspace-relative file into observation fields."""

    name = "workspace_read"
    params_model = WorkspaceReadParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = (
            params
            if isinstance(params, WorkspaceReadParams)
            else WorkspaceReadParams.model_validate(
                params.model_dump() if isinstance(params, BaseModel) else params
            )
        )
        paths = _workspace_from_runtime(runtime)
        rel = body.path
        try:
            target = paths.resolve(rel)
        except ValueError as exc:
            return {
                "path": rel,
                "exists": False,
                "text": None,
                "workspace_root": str(paths.root),
                "error": str(exc),
            }
        exists = target.is_file()
        text: str | None = None
        if exists:
            text = target.read_text(encoding="utf-8")
        return {
            "path": rel,
            "exists": exists,
            "text": text,
            "workspace_root": str(paths.root),
        }


def workspace_cli_verb_classes() -> dict[str, type[CliVerb]]:
    return {
        RunPythonVerb.name: RunPythonVerb,
        WorkspaceReadVerb.name: WorkspaceReadVerb,
    }


__all__ = [
    "RunPythonParams",
    "RunPythonVerb",
    "WorkspaceReadParams",
    "WorkspaceReadVerb",
    "workspace_cli_verb_classes",
]
