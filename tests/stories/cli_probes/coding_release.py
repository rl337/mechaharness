"""Observe coding-release contracts using disposable workspaces and offline inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mechaharness.cli_verb import CliProbe
from mechaharness.coding_git import LocalProcessCodingGit, RecordingPullRequestCodingGit
from mechaharness.coding_workspace_checkpoint import (
    restore_coding_workspace_checkpoint,
    save_coding_workspace_checkpoint,
)
from mechaharness.config import Settings
from mechaharness.core.access import FsRead, GraphEscalate, GraphExecute
from mechaharness.di import get_injector
from mechaharness.durable_graph_generator import DurableGraphGenerator
from mechaharness.gastronomic_comparison import (
    assemble_gastronomic_trial,
    summarize_gastronomic_comparison,
    trial_from_suite_run,
)
from mechaharness.mcp_graph_driver import GeneratorMcpServer
from mechaharness.project_coding import ProjectCodingConfig


class NoParams(BaseModel, extra="forbid"):
    pass


def _offline_settings() -> Settings:
    return Settings(inference_backend="mock", api_key=None, base_url=None)


def _run(
    config: ProjectCodingConfig, goal: str, *, run_id: str = "coding-release", **inputs: Any
) -> dict[str, Any]:
    server = GeneratorMcpServer(get_injector(config).inject(DurableGraphGenerator))
    run = {"run_id": run_id, "controller_id": "story"}
    start = server.call_tool(
        "generator_start", {**run, "recipe_id": "guided_coding", "inputs": {"goal": goal, **inputs}}
    )
    return server.call_tool(
        "generator_resume",
        {
            **run,
            "choice_id": "minimal",
            "expected_sequence": start["sequence"],
            "request_id": start["request_id"],
        },
    )


class RestoreProbe(CliProbe):
    name = "recover_coding_checkout"
    params_model = NoParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        repo = Path(runtime.workspace_root) / "checkout"
        save_coding_workspace_checkpoint(repo)
        (repo / "target.py").write_text("broken attempt")
        (repo / "notes.txt").write_text("second session edit")
        (repo / "untracked.txt").write_text("second session addition")
        restored = restore_coding_workspace_checkpoint(
            repo, writes={"target.py": b"broken attempt"}
        )
        return {
            "restored": restored,
            "source": (repo / "target.py").read_text(),
            "note": (repo / "notes.txt").read_text(),
            "addition": (repo / "untracked.txt").exists(),
        }


class PathParams(BaseModel, extra="forbid"):
    path: str


class VerifyBoundaryProbe(CliProbe):
    name = "verify_coding_path"
    params_model = PathParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        assert isinstance(params, PathParams)
        parent = Path(runtime.workspace_root)
        root = parent / "repo"
        root.mkdir(exist_ok=True)
        canary = parent / "canary"
        canary.write_text("outside evidence")
        link = root / "linked"
        if not link.is_symlink():
            link.symlink_to(canary)
        config = ProjectCodingConfig(
            settings=_offline_settings(),
            workspace=root,
            completer=lambda *_: {"role": "assistant", "content": "done"},
        )
        result = _run(
            config,
            "Inspect workspace evidence",
            max_repair_rounds=0,
            verify_runs=[{"path": params.path, "text_contains": "outside evidence"}],
        )
        return {"completed": result["kind"] == "completed"}


class ProviderProbe(CliProbe):
    name = "start_without_coding_provider"
    params_model = NoParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        root = Path(runtime.workspace_root)
        config = ProjectCodingConfig(settings=_offline_settings(), workspace=root)
        result = _run(config, "Write release notes")
        return {
            "terminal": result["kind"],
            "demo_file_created": (root / ".mechaharness/guided_coding_stub.txt").exists(),
        }


class DeniedEffectsProbe(CliProbe):
    name = "attempt_denied_coding_tools"
    params_model = NoParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        root = Path(runtime.workspace_root)
        git = RecordingPullRequestCodingGit(LocalProcessCodingGit(workspace=root))
        calls = iter(
            [
                ("run_shell", {"command": "echo effect > shell-marker"}),
                ("create_pull_request", {"title": "Unauthorized", "body": "offline recording"}),
            ]
        )

        def complete(*_: Any) -> dict[str, Any]:
            call = next(calls, None)
            if not call:
                return {"role": "assistant", "content": "done"}
            name, args = call
            return {
                "role": "assistant",
                "tool_calls": [{"id": name, "function": {"name": name, "arguments": args}}],
            }

        class ReadOnlyHost(ProjectCodingConfig):
            def get_grants(self) -> list[object]:
                return [FsRead, GraphExecute, GraphEscalate]

        config = ReadOnlyHost(
            settings=_offline_settings(), workspace=root, completer=complete, coding_git=git
        )
        _run(config, "Inspect the package")
        return {"shell_executed": (root / "shell-marker").exists(), "published": len(git.created)}


class TrialParams(BaseModel, extra="forbid"):
    budget_key: str


class ComparisonProbe(CliProbe):
    name = "compare_coding_trials"
    params_model = TrialParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        assert isinstance(params, TrialParams)
        batch = json.loads((Path(runtime.workspace_root) / "batch.json").read_text())
        trials = []
        for repeat, metrics in enumerate(batch["metrics"]):
            for arm, recipe, budget in (
                ("A", "guided_coding", batch["budget"]),
                ("B", "gastronomic_guided_development", batch[params.budget_key]),
            ):
                trials.append(
                    assemble_gastronomic_trial(
                        trial_id=f"{arm}-{repeat}",
                        arm=arm,
                        recipe_id=recipe,
                        suite_id="package-issue",
                        model=batch["model"],
                        budget=budget,
                        metrics=metrics,
                    )
                )
        summary = summarize_gastronomic_comparison(trials)
        return {
            "arm_a_count": summary["arms"]["A"]["n"],
            "arm_b_success_rate": summary["arms"]["B"]["success_rate"],
            "comparable": summary["comparable_ab"],
            "automatic_winner": summary["winner"] is not None,
        }


class TrialMetricsProbe(CliProbe):
    name = "record_coding_trial_metrics"
    params_model = NoParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        trial = trial_from_suite_run(
            runtime.workspace_root,
            trial_id="package-trial",
            arm="A",
            recipe_id="guided_coding",
            stages_total=2,
        )
        return dict(trial["metrics"])


class RepairPromptProbe(CliProbe):
    name = "repair_package_after_failed_check"
    params_model = NoParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        root = Path(runtime.workspace_root)
        attempts = iter(["return 0", None, "return value + 1", None])
        prompts: list[str] = []

        def complete(messages: list[dict[str, Any]], *_: Any) -> dict[str, Any]:
            prompts.extend(
                str(msg.get("content") or "") for msg in messages if msg.get("role") == "user"
            )
            body = next(attempts, None)
            if body is None:
                return {"role": "assistant", "content": "done"}
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "edit",
                        "function": {
                            "name": "write_file",
                            "arguments": {
                                "path": "counts.py",
                                "content": f"def increment(value):\n    {body}\n",
                            },
                        },
                    }
                ],
            }

        config = ProjectCodingConfig(
            settings=_offline_settings(), workspace=root, completer=complete
        )
        result = _run(
            config,
            "Fix increment in counts.py and preserve its prior tests",
            verify_runs=[{"pytest": True, "path": "tests"}],
            max_repair_rounds=1,
        )
        briefs = [p for p in prompts if "Host verify failed" in p]
        return {
            "terminal": result["kind"],
            "repair_observed": bool(briefs),
            "check_identified": any("tests" in p for p in briefs),
            "calculator_advice": any("def evaluate(expr)" in p for p in briefs),
        }


class OverlappingRunsProbe(CliProbe):
    """Schedule the second handoff between the first edit and its failed verify."""

    name = "interleave_coding_sessions"
    params_model = NoParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        root = Path(runtime.workspace_root)
        second_result: dict[str, Any] = {}
        writes = iter([("notes.txt", "second session edit"), ("new.txt", "new draft")])

        def write(path: str, content: str) -> dict[str, Any]:
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": path,
                        "function": {
                            "name": "write_file",
                            "arguments": {
                                "path": path,
                                "content": content,
                            },
                        },
                    }
                ],
            }

        def second(*_: Any) -> dict[str, Any]:
            change = next(writes, None)
            return write(*change) if change else {"role": "assistant", "content": "done"}

        first_edit_sent = False

        def first(*_: Any) -> dict[str, Any]:
            nonlocal first_edit_sent
            if not first_edit_sent:
                first_edit_sent = True
                return write("target.txt", "broken attempt")
            if not second_result:
                config = ProjectCodingConfig(
                    settings=_offline_settings(), workspace=root, completer=second
                )
                second_result.update(
                    _run(
                        config,
                        "Write the two draft notes",
                        run_id="drafts",
                        verify_runs=[
                            {"path": "notes.txt", "text_contains": "second session edit"},
                            {"path": "new.txt", "text_contains": "new draft"},
                        ],
                    )
                )
            return {"role": "assistant", "content": "done"}

        config = ProjectCodingConfig(settings=_offline_settings(), workspace=root, completer=first)
        result = _run(
            config,
            "Fix target.txt",
            max_repair_rounds=0,
            verify_runs=[{"path": "target.txt", "text_contains": "verified fix"}],
        )
        addition = root / "new.txt"
        return {
            "first_stopped": result["kind"] in {"advice_requested", "failed"},
            "second_completed": second_result.get("kind") == "completed",
            "source": (root / "target.txt").read_text(),
            "note": (root / "notes.txt").read_text(),
            "addition": addition.read_text() if addition.exists() else None,
        }
