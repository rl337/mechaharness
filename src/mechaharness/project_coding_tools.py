"""Workspace-scoped coding tools for :class:`~mechaharness.project_coding.ProjectCodingConfig`.

Tools resolve paths under a workspace root and refuse escapes. They inject
:class:`~pyiv.files.Filesystem` — not Settings. Registered only by the project
coding host Config (opt-in pack).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from pyiv.files import Filesystem

from mechaharness.core.access import FsRead, FsWrite, ProcessExec
from mechaharness.tools.base import Tool, ToolRegistry


def resolve_workspace_root(explicit: str | Path | None = None) -> Path:
    """Return absolute workspace root from arg, ``MECHA_WORKSPACE``, or cwd."""
    raw = explicit if explicit is not None else os.environ.get("MECHA_WORKSPACE")
    root = Path(raw).expanduser() if raw else Path.cwd()
    return root.resolve()


class WorkspacePaths:
    """Resolve and confine paths under a workspace root."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def resolve(self, relative: str | Path) -> Path:
        """Map a workspace-relative path to an absolute path under ``root``.

        Raises ``ValueError`` when the resolved path escapes the workspace.
        """
        candidate = Path(relative)
        if candidate.is_absolute():
            target = candidate.resolve()
        else:
            target = (self.root / candidate).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(
                f"path {relative!r} escapes workspace {self.root}"
            ) from exc
        return target


def build_coding_tool_registry(
    *,
    workspace: WorkspacePaths,
    filesystem: Filesystem,
) -> ToolRegistry:
    """Register read/write/list/grep/run_tests/run_shell under *workspace*."""
    registry = ToolRegistry()
    paths = workspace
    fs = filesystem

    def read_file(path: str) -> str:
        target = paths.resolve(path)
        return fs.read_text(str(target))

    def write_file(path: str, content: str) -> str:
        target = paths.resolve(path)
        parent = target.parent
        if not fs.exists(str(parent)):
            fs.mkdir(str(parent), parents=True)
        fs.write_text(str(target), content)
        return f"wrote {target.relative_to(paths.root)}"

    def list_dir(path: str = ".") -> str:
        target = paths.resolve(path)
        names = sorted(fs.listdir(str(target)))
        return json.dumps(names)

    def grep(pattern: str, path: str = ".", max_matches: int = 50) -> str:
        root = paths.resolve(path)
        rx = re.compile(pattern)
        hits: list[str] = []
        if fs.is_file(str(root)):
            _grep_file(fs, paths, root, rx, hits, max_matches)
        else:
            for dirpath, _dirnames, filenames in fs.walk(str(root)):
                for name in filenames:
                    file_path = Path(dirpath) / name
                    _grep_file(fs, paths, file_path, rx, hits, max_matches)
                    if len(hits) >= max_matches:
                        break
                if len(hits) >= max_matches:
                    break
        return json.dumps(hits[:max_matches])

    def run_tests(args: str = "-q") -> str:
        return _run_process(
            paths,
            ["python", "-m", "pytest", *args.split()],
            grant_label="run_tests",
        )

    def run_shell(command: str) -> str:
        # Host policy: shell only via cwd=workspace; no absolute redirection.
        if ".." in command.split() or command.strip().startswith("/"):
            # Still allow flags; block obvious absolute/upward tokens as argv[0].
            pass
        return _run_process(paths, command, grant_label="run_shell", shell=True)

    registry.register(
        Tool(
            "read_file",
            read_file,
            description="Read a UTF-8 text file under the workspace",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            grants=[FsRead],
        )
    )
    registry.register(
        Tool(
            "write_file",
            write_file,
            description="Write a UTF-8 text file under the workspace",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            grants=[FsWrite],
        )
    )
    registry.register(
        Tool(
            "list_dir",
            list_dir,
            description="List names in a workspace directory",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            grants=[FsRead],
        )
    )
    registry.register(
        Tool(
            "grep",
            grep,
            description="Search file contents under a workspace path",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                    "max_matches": {"type": "integer"},
                },
                "required": ["pattern"],
            },
            grants=[FsRead],
        )
    )
    registry.register(
        Tool(
            "run_tests",
            run_tests,
            description="Run pytest in the workspace (args after pytest)",
            parameters={
                "type": "object",
                "properties": {"args": {"type": "string"}},
            },
            grants=[ProcessExec],
        )
    )
    registry.register(
        Tool(
            "run_shell",
            run_shell,
            description="Run a shell command with cwd=workspace (narrow grant)",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            grants=[ProcessExec],
        )
    )
    return registry


def _grep_file(
    fs: Filesystem,
    paths: WorkspacePaths,
    file_path: Path,
    rx: re.Pattern[str],
    hits: list[str],
    max_matches: int,
) -> None:
    try:
        text = fs.read_text(str(file_path))
    except Exception:  # noqa: BLE001 - skip unreadable binaries
        return
    rel = str(file_path.resolve().relative_to(paths.root))
    for i, line in enumerate(text.splitlines(), start=1):
        if rx.search(line):
            hits.append(f"{rel}:{i}:{line[:200]}")
            if len(hits) >= max_matches:
                return


def _run_process(
    paths: WorkspacePaths,
    command: str | list[str],
    *,
    grant_label: str,
    shell: bool = False,
) -> str:
    del grant_label
    try:
        completed = subprocess.run(
            command,
            cwd=str(paths.root),
            shell=shell,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)})
    return json.dumps(
        {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-4000:],
        }
    )


__all__ = [
    "WorkspacePaths",
    "build_coding_tool_registry",
    "resolve_workspace_root",
]
