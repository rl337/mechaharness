"""Exercise a coding handoff over the same MCP operations a host uses."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pydantic import BaseModel, ConfigDict

from mechaharness.cli_verb import CliVerb
from mechaharness.durable_generator_host import build_host_generator
from mechaharness.durable_graph_generator import FileGeneratorRunStore
from mechaharness.generator_local_work import GeneratorLocalWork
from mechaharness.mcp_graph_driver import GeneratorMcpServer


class PackageDiff:
    """Use a private Git index to check the handoff from its starting tree."""

    def __init__(self, workspace: Path, scratch: Path) -> None:
        self.workspace = workspace
        self.git_dir = scratch / "index.git"
        self.clean = scratch / "replay"
        self.clean.mkdir()
        self.git("init", "--quiet")
        self.base = self.snapshot()

    def git(self, *args: str, cwd: Path | None = None) -> bytes:
        root = cwd or self.workspace
        return subprocess.check_output(
            ["git", f"--git-dir={self.git_dir}", f"--work-tree={root}", *args],
            cwd=root,
        )

    def snapshot(self) -> str:
        self.git(
            "add",
            "-A",
            "--",
            ".",
            ":(exclude).mechaharness",
            ":(exclude)**/__pycache__/**",
            ":(exclude).pytest_cache",
        )
        return self.git("write-tree").decode().strip()

    def verify(self) -> dict[str, Any]:
        updated = self.snapshot()
        names = self.git("diff", "--name-only", self.base, updated)
        patch = self.git("diff", "--binary", self.base, updated)
        self.git("read-tree", self.base)
        self.git("checkout-index", "--all", "--force", cwd=self.clean)
        if patch:
            subprocess.run(["git", "apply", "-"], cwd=self.clean, input=patch, check=True)
        check = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=self.clean,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "diff_paths": names.decode().splitlines(),
            "clean_exit": check.returncode,
            "clean_output": check.stdout + check.stderr,
        }


class HandoffParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs: dict[str, Any]


def mcp_handoff_verb(local_work: GeneratorLocalWork) -> type[CliVerb]:
    class HandoffVerb(CliVerb):
        name = "mcp_coding_handoff"
        params_model = HandoffParams

        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            assert isinstance(params, HandoffParams)
            with TemporaryDirectory() as directory:
                store = Path(directory) / "runs.json"

                def server() -> GeneratorMcpServer:
                    generator = build_host_generator(
                        run_store=FileGeneratorRunStore(store), local_work=local_work
                    )
                    return GeneratorMcpServer(generator)

                package = PackageDiff(Path(runtime.workspace_root), Path(directory))
                run = {"run_id": "package-issue", "controller_id": "story"}
                start = server().call_tool(
                    "generator_start",
                    {**run, "recipe_id": "guided_coding", "inputs": params.inputs},
                )
                resumed = server()
                inspection = resumed.call_tool("generator_inspect", {"run_id": run["run_id"]})
                answer = {
                    **run,
                    "expected_sequence": start["sequence"],
                    "request_id": start["request_id"],
                    "choice_id": "minimal",
                    "idempotency_key": "package-issue-answer",
                }
                result = resumed.call_tool("generator_resume", answer)

                # Count actual workspace changes across a replay, including a
                # repeated write of identical bytes (mtime changes).
                def file_versions() -> dict[Path, int]:
                    root = Path(runtime.workspace_root)
                    return {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}

                before = file_versions()
                replay = server().call_tool("generator_resume", answer)
                changed_on_replay = before != file_versions()
                return {
                    **package.verify(),
                    "start": start["kind"],
                    "recovered_request": inspection["pending_request"]["request_id"]
                    == start["request_id"],
                    "terminal": result["kind"],
                    "written_files": result["payload"].get("written_files"),
                    "replay_equal": replay == result,
                    "replay_changed_files": changed_on_replay,
                }

    return HandoffVerb
