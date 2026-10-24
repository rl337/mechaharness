"""Unit tests for project coding tools, Config, and generator local work."""

from __future__ import annotations

import json
from pathlib import Path

from pyiv.files import MemoryFilesystem

from mechaharness.di import get_injector
from mechaharness.durable_graph_generator import DurableGraphGenerator, GuidanceResponse
from mechaharness.generator_local_work import ProjectCodingLocalWork
from mechaharness.project_coding import ProjectCodingConfig
from mechaharness.project_coding_tools import (
    WorkspacePaths,
    build_coding_tool_registry,
)


def test_workspace_paths_rejects_escape(tmp_path: Path) -> None:
    paths = WorkspacePaths(tmp_path)
    try:
        paths.resolve("../outside.txt")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_coding_git_tools_status_log_diff(tmp_path: Path) -> None:
    import subprocess

    from pyiv.files import RealFilesystem

    from mechaharness.coding_git import LocalProcessCodingGit

    root = tmp_path
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    main = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (root / "a.txt").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "change"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    tools = build_coding_tool_registry(
        workspace=WorkspacePaths(root),
        filesystem=RealFilesystem(),
        coding_git=LocalProcessCodingGit(workspace=root),
    )
    status = json.loads(tools.get("git_status").handler())
    assert status["ok"] is True
    assert main in status["stdout"]
    # Empty range vs HEAD itself: use HEAD~1 as base.
    log = json.loads(tools.get("git_log").handler(base="HEAD~1"))
    assert log["ok"] is True
    assert "change" in log["stdout"]
    diff = json.loads(tools.get("git_diff").handler(base="HEAD~1", stat_only=True))
    assert diff["ok"] is True
    assert "a.txt" in diff["stdout"]
    bad = json.loads(tools.get("git_log").handler(base="origin/main; rm -rf /"))
    assert bad["ok"] is False


def test_coding_git_injectable_fake_binding(tmp_path: Path) -> None:
    """Hosts can swap CodingGit without changing tool names."""
    from pyiv.files import RealFilesystem

    from mechaharness.coding_git import CodingGit, CodingGitResult
    from mechaharness.di import get_injector
    from mechaharness.project_coding import ProjectCodingConfig

    class _FakeGit(CodingGit):
        def status(self) -> CodingGitResult:
            return CodingGitResult(ok=True, stdout="## fake\n")

        def log(self, *, base: str = "origin/main", max_count: int = 40) -> CodingGitResult:
            del base, max_count
            return CodingGitResult(ok=True, stdout="abc fake\n")

        def diff(
            self,
            *,
            base: str = "origin/main",
            stat_only: bool = True,
            max_bytes: int = 120_000,
        ) -> CodingGitResult:
            del base, stat_only, max_bytes
            return CodingGitResult(ok=True, stdout=" fake.py | 1 +\n")

        def push(
            self, *, remote: str = "origin", set_upstream: bool = True
        ) -> CodingGitResult:
            del remote, set_upstream
            return CodingGitResult(ok=True, stdout="pushed\n")

        def create_pull_request(
            self,
            *,
            title: str,
            body: str,
            base: str = "main",
            draft: bool = False,
        ) -> CodingGitResult:
            del body, base, draft
            return CodingGitResult(
                ok=True, stdout="https://example.test/pr/1\n", extra={"title": title}
            )

    fake = _FakeGit()
    cfg = ProjectCodingConfig(workspace=tmp_path, coding_git=fake)
    inj = get_injector(cfg)
    bound = inj.inject(CodingGit)
    assert bound is fake
    tools = cfg.get_tools()
    assert "fake" in json.loads(tools.get("git_status").handler())["stdout"]
    pr = json.loads(
        tools.get("create_pull_request").handler(title="T", body="B")
    )
    assert pr["ok"] is True
    assert "example.test/pr/1" in pr["stdout"]
    # RealFilesystem unused beyond registry build path
    del RealFilesystem


def test_coding_tools_read_write_list_grep(tmp_path: Path) -> None:
    fs = MemoryFilesystem()
    # MemoryFilesystem is absolute-key oriented; root tools at tmp_path strings.
    root = tmp_path
    fs.mkdir(str(root), parents=True)
    paths = WorkspacePaths(root)
    # Seed via real disk for RealFilesystem paths; use RealFilesystem instead.
    from pyiv.files import RealFilesystem

    fs = RealFilesystem()
    tools = build_coding_tool_registry(workspace=paths, filesystem=fs)
    assert tools.get("write_file").handler(path="a/hello.txt", content="hello world\n")
    assert "hello world" in tools.get("read_file").handler(path="a/hello.txt")
    listed = json.loads(tools.get("list_dir").handler(path="a"))
    assert "hello.txt" in listed
    hits = json.loads(tools.get("grep").handler(pattern="hello", path="."))
    assert any("hello.txt" in h for h in hits)


def test_project_coding_config_registers_guided_coding() -> None:
    cfg = ProjectCodingConfig(workspace=".")
    assert "guided_coding" in cfg.graph_template_classes()
    injector = get_injector(cfg)
    gen = injector.inject(DurableGraphGenerator)
    ids = {r.recipe_id for r in gen.list_recipes()}
    assert "guided_coding" in ids


def test_guided_coding_local_work_writes_file(tmp_path: Path) -> None:
    from pyiv.files import RealFilesystem

    fs = RealFilesystem()
    # Force offline stub complete (ignore any machine .env base_url).
    stub = _offline_write_stub()
    cfg = ProjectCodingConfig(workspace=tmp_path, filesystem=fs, completer=stub)  # type: ignore[arg-type]
    injector = get_injector(cfg)
    gen = injector.inject(DurableGraphGenerator)
    y1 = gen.start(
        "guided_coding",
        {"goal": "write stub marker", "task": "write stub marker"},
        controller_id="unit",
        run_id="guided-unit-1",
    )
    assert y1.kind == "advice_requested"
    y2 = gen.resume(
        y1.run_id,
        GuidanceResponse(request_id=y1.request_id or "", choice_id="minimal"),
        expected_sequence=y1.sequence,
        controller_id="unit",
        idempotency_key="guided-unit-1:1",
    )
    assert y2.kind == "completed"
    assert y2.payload.get("result") == "ok"
    assert ".mechaharness/guided_coding_stub.txt" in (
        y2.payload.get("written_files") or []
    )
    stub = tmp_path / ".mechaharness" / "guided_coding_stub.txt"
    assert stub.is_file()
    assert "guided_coding ok" in stub.read_text()


def _offline_write_stub() -> object:
    """Minimal Completer duck that triggers write_file then finishes."""

    class _Stub:
        def complete(self, messages: object) -> dict:
            del messages
            if not getattr(self, "_wrote", False):
                self._wrote = True
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_write",
                            "function": {
                                "name": "write_file",
                                "arguments": {
                                    "path": ".mechaharness/guided_coding_stub.txt",
                                    "content": "guided_coding ok\n",
                                },
                            },
                        }
                    ],
                }
            return {"role": "assistant", "content": "done", "tool_calls": []}

    return _Stub()


def test_parse_prompt_tool_calls_balanced_json() -> None:
    from mechaharness.project_coding import _parse_prompt_tool_calls

    content = (
        '<tool_call>\n'
        '{"name": "write_file", "arguments": {"path": "a.py", '
        '"content": "class X:\\n    def f(self):\\n        return {}\\n"}}\n'
        "</tool_call>"
    )
    calls = _parse_prompt_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "write_file"
    assert "class X" in calls[0]["function"]["arguments"]["content"]


def test_coding_ci_tools_register_with_recording_github(tmp_path: Path) -> None:
    """ci_checks / ci_job_log register when a GitHubClient is bound."""
    import json

    from pyiv.files import RealFilesystem

    from mechaharness.github_client import RecordingGitHubClient
    from mechaharness.github_connection import GitHubConnectionConfig

    github = RecordingGitHubClient()
    tools = build_coding_tool_registry(
        workspace=WorkspacePaths(tmp_path),
        filesystem=RealFilesystem(),
        github=github,
        github_connection=GitHubConnectionConfig(
            token="story-mock", owner="acme", repo="demo"
        ),
    )
    assert "ci_checks" in tools
    assert "ci_job_log" in tools
    checks = json.loads(tools.get("ci_checks").handler(ref="abc"))
    assert checks["ok"] is True
    assert checks["extra"]["failed"][0]["job_id"] == RecordingGitHubClient.DEFAULT_JOB_ID
    logs = json.loads(
        tools.get("ci_job_log").handler(
            job_id=RecordingGitHubClient.DEFAULT_JOB_ID, max_bytes=8_000
        )
    )
    assert logs["ok"] is True
    assert "Ruff" in logs["stdout"]
    assert [c["op"] for c in github.calls] == [
        "list_check_runs",
        "get_workflow_job_logs",
    ]


def test_project_coding_verify_runs_repair(tmp_path: Path) -> None:
    """Host verify_runs failure triggers one repair coding burst."""
    from pyiv.files import RealFilesystem

    from mechaharness.durable_graph_generator import GeneratorRunRecord

    fs = RealFilesystem()
    tools = build_coding_tool_registry(
        workspace=WorkspacePaths(tmp_path), filesystem=fs
    )
    state = {"n": 0}

    def complete(messages: object, meta: object) -> dict:
        del meta
        state["n"] += 1
        # First item: write broken calc. Repair item: write good calc.
        content = "print(9)\n" if state["n"] == 1 else "print(0)\n"
        if state["n"] in {1, 3}:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"w{state['n']}",
                        "function": {
                            "name": "write_file",
                            "arguments": {"path": "calc.py", "content": content},
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "done", "tool_calls": []}

    work = ProjectCodingLocalWork(
        tools=tools, complete=complete, workspace_root=tmp_path, max_iterations=4
    )
    out = work.run(
        GeneratorRunRecord(
            run_id="verify",
            recipe_id="guided_coding",
            graph_id="g",
            controller_id="c",
            inputs={
                "goal": "Write calc.py that prints 0",
                "max_iterations": 4,
                "verify_runs": [
                    {
                        "path": "calc.py",
                        "args": [],
                        "stdout_contains": "0",
                        "exit_code": 0,
                    }
                ],
            },
            guidance_history=[{"response": {"choice_id": "minimal"}}],
        )
    )
    assert out.get("result") == "ok"
    assert (tmp_path / "calc.py").read_text() == "print(0)\n"
    assert any(
        str(r.get("item_id") or "").startswith("verify_repair")
        for r in out.get("item_results") or []
    )


def test_project_coding_verify_text_contains_repair(tmp_path: Path) -> None:
    """Missing required symbols in file text trigger verify_repair."""
    from pyiv.files import RealFilesystem

    from mechaharness.durable_graph_generator import GeneratorRunRecord

    fs = RealFilesystem()
    tools = build_coding_tool_registry(
        workspace=WorkspacePaths(tmp_path), filesystem=fs
    )
    state = {"n": 0}
    bad = "def evaluate(expr):\n    return float(expr)\n"
    good = (
        "def evaluate(expr):\n    return float(expr)\n\n"
        "def main(argv=None):\n    return 0\n"
    )

    def complete(messages: object, meta: object) -> dict:
        del meta
        state["n"] += 1
        content = bad if state["n"] == 1 else good
        if state["n"] in {1, 3}:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"w{state['n']}",
                        "function": {
                            "name": "write_file",
                            "arguments": {"path": "calc.py", "content": content},
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "done", "tool_calls": []}

    work = ProjectCodingLocalWork(
        tools=tools, complete=complete, workspace_root=tmp_path, max_iterations=4
    )
    out = work.run(
        GeneratorRunRecord(
            run_id="shape",
            recipe_id="guided_coding",
            graph_id="g",
            controller_id="c",
            inputs={
                "goal": "Write calc.py with evaluate and main",
                "max_iterations": 4,
                "verify_runs": [
                    {"path": "calc.py", "text_contains": ["def evaluate", "def main"]}
                ],
            },
            guidance_history=[{"response": {"choice_id": "minimal"}}],
        )
    )
    assert out.get("result") == "ok"
    assert "def main" in (tmp_path / "calc.py").read_text()
    assert any(
        str(r.get("item_id") or "").startswith("verify_repair")
        for r in out.get("item_results") or []
    )


def test_project_coding_write_recovery_nudge(tmp_path: Path) -> None:
    """If the model finishes without write_file, one recovery burst forces it."""
    from pyiv.files import RealFilesystem

    from mechaharness.durable_graph_generator import GeneratorRunRecord

    fs = RealFilesystem()
    tools = build_coding_tool_registry(
        workspace=WorkspacePaths(tmp_path), filesystem=fs
    )
    state = {"round": 0}

    def complete(messages: object, meta: object) -> dict:
        del meta
        state["round"] += 1
        # First burst: claim done with no tools. Recovery: write.
        if state["round"] == 1:
            return {"role": "assistant", "content": "done", "tool_calls": []}
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_write",
                    "function": {
                        "name": "write_file",
                        "arguments": {
                            "path": "calc.py",
                            "content": "print(1)\n",
                        },
                    },
                }
            ],
        }

    work = ProjectCodingLocalWork(
        tools=tools, complete=complete, workspace_root=tmp_path, max_iterations=4
    )
    out = work.run(
        GeneratorRunRecord(
            run_id="recover",
            recipe_id="guided_coding",
            graph_id="g",
            controller_id="c",
            inputs={"goal": "Update calc.py with a print", "max_iterations": 4},
            guidance_history=[{"response": {"choice_id": "minimal"}}],
        )
    )
    assert out.get("result") == "ok"
    assert "calc.py" in (out.get("written_files") or [])
    assert (tmp_path / "calc.py").read_text() == "print(1)\n"
    assert state["round"] >= 2


def test_project_coding_local_work_skips_other_recipes() -> None:
    work = ProjectCodingLocalWork(
        tools=build_coding_tool_registry(
            workspace=WorkspacePaths("."),
            filesystem=MemoryFilesystem(),
        ),
        complete=lambda messages, meta: {"role": "assistant", "content": "x", "tool_calls": []},
    )
    from mechaharness.durable_graph_generator import GeneratorRunRecord

    out = work.run(
        GeneratorRunRecord(
            run_id="r",
            recipe_id="demo_guidance",
            graph_id="g",
            controller_id="c",
        )
    )
    assert out.get("skipped") is True
