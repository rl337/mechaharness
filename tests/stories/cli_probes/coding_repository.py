"""Exercise the production MCP workspace with a deterministic model reply."""

from __future__ import annotations

import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from pydantic import BaseModel

from mechaharness.cli_verb import CliProbe
from mechaharness.config import Settings
from mechaharness.isolation.coding_repository import CodingRepositoryIsolation
from mechaharness.isolation.workspace_isolation import WorkspaceIsolationHandle
from mechaharness.mcp_graph_driver import GeneratorMcpServer, build_generator
from mechaharness.project_coding import ProjectCodingConfig


class RepositoryEdit(BaseModel, extra="forbid"):
    path: str
    original: str
    dirty: str
    replacement: str


class RepositoryHandoffProbe(CliProbe):
    name = "review_repository_patch"
    params_model = RepositoryEdit

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        assert isinstance(params, RepositoryEdit)
        repo = Path(runtime.workspace_root)
        target = repo / params.path
        target.write_text(params.original)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "add", "--", params.path], cwd=repo, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Story",
                "-c",
                "user.email=story@example.test",
                "commit",
                "-qm",
                "base",
            ],
            cwd=repo,
            check=True,
        )
        target.write_text(params.dirty)
        (repo / "draft.txt").write_text("untracked draft")
        calls = []

        def complete(*_: Any) -> dict[str, Any]:
            calls.append(True)
            if len(calls) == 1:
                return {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "edit",
                            "function": {
                                "name": "write_file",
                                "arguments": {
                                    "path": params.path,
                                    "content": params.replacement,
                                },
                            },
                        }
                    ],
                }
            return {"role": "assistant", "content": "done"}

        class OfflineHost(ProjectCodingConfig):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(
                    **kwargs, settings=Settings(inference_backend="mock"), completer=complete
                )

        with (
            TemporaryDirectory() as temp,
            patch.dict(os.environ, MECHA_WORKSPACE=str(repo)),
            patch("mechaharness.project_coding.mcp_host_config_class", return_value=OfflineHost),
        ):

            def server() -> GeneratorMcpServer:
                return GeneratorMcpServer(build_generator(store_path=Path(temp) / "runs.json"))

            run = {"run_id": "patch-review", "controller_id": "owner"}
            start = server().call_tool(
                "generator_start",
                {
                    **run,
                    "recipe_id": "guided_coding",
                    "inputs": {
                        "goal": f"Fix {params.path} while retaining the draft change",
                        "verify_runs": [
                            {"path": params.path, "text_contains": params.replacement},
                            {"path": "draft.txt", "text_contains": "untracked draft"},
                        ],
                    },
                },
            )
            answer = {
                **run,
                "choice_id": "minimal",
                "request_id": start["request_id"],
                "expected_sequence": start["sequence"],
                "idempotency_key": "same-answer",
            }
            barrier = threading.Barrier(2)

            def resume() -> dict[str, Any]:
                restarted = server()
                barrier.wait(timeout=10)
                return restarted.call_tool("generator_resume", answer)

            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = [pool.submit(resume) for _ in range(2)]
                first, second = [future.result() for future in pending]
            result = first["payload"]
            workspace = Path(result["workspace_root"])
            try:
                patch_file = Path(result["patch_path"])
                check = subprocess.run(["git", "apply", "--check", str(patch_file)], cwd=repo)
                return {
                    "terminal": first["kind"],
                    "replayed": first == second,
                    "model_calls": len(calls),
                    "written_files": result["written_files"],
                    "base_revision_matches": result["base_revision"]
                    == subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
                    ).strip(),
                    "patch_applies": check.returncode == 0,
                    "private_file": (workspace / params.path).read_text(),
                    "source_file": target.read_text(),
                    "source_draft": (repo / "draft.txt").read_text(),
                }
            finally:
                CodingRepositoryIsolation(repo).release(
                    WorkspaceIsolationHandle(
                        label="patch-review", provider_kind="git_clone", root_ref=str(workspace)
                    )
                )
