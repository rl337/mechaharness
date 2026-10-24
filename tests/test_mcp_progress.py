"""MCP progress path formatting and stdio notifications."""

from __future__ import annotations

import io
import json
from pathlib import Path

from pyiv.files import RealFilesystem

from mechaharness.di import get_injector
from mechaharness.durable_graph_generator import DurableGraphGenerator
from mechaharness.mcp_graph_driver import GeneratorMcpServer
from mechaharness.mcp_progress import (
    coding_progress_prefix,
    format_progress_path,
    mcp_progress_scope,
    report_mcp_progress,
)
from mechaharness.project_coding import ProjectCodingConfig


def test_format_progress_path_joins_segments() -> None:
    assert (
        format_progress_path(
            ["guided_coding", "plan_tile", "work_item 4", "tool_round 3", "write_file"]
        )
        == "guided_coding › plan_tile › work_item 4 › tool_round 3 › write_file"
    )
    assert format_progress_path(["", " a ", ""]) == "a"


def test_coding_progress_prefix_guided_vs_plan() -> None:
    assert coding_progress_prefix("guided_coding") == ["guided_coding", "plan_tile"]
    assert coding_progress_prefix("instruction_todo_plan") == [
        "instruction_todo_plan"
    ]


def test_mcp_progress_scope_emits_notifications() -> None:
    out: list[dict] = []

    def write(msg: dict) -> None:
        out.append(msg)

    with mcp_progress_scope("tok-1", write, base_segments=["guided_coding"]) as prog:
        assert prog is not None
        report_mcp_progress("plan_tile", "work_item 1", "tool_round 1", "inference")
        report_mcp_progress("plan_tile", "work_item 1", "tool_round 1", "write_file")

    assert len(out) == 2
    assert out[0]["method"] == "notifications/progress"
    assert out[0]["params"]["progressToken"] == "tok-1"
    assert out[0]["params"]["progress"] == 1.0
    assert (
        out[0]["params"]["message"]
        == "guided_coding › plan_tile › work_item 1 › tool_round 1 › inference"
    )
    assert "write_file" in out[1]["params"]["message"]
    assert out[1]["params"]["progress"] == 2.0


def _offline_write_stub() -> object:
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


def test_mcp_tools_call_emits_progress_during_guided_coding(
    tmp_path: Path,
) -> None:
    """Cursor-style tools/call with progressToken keeps notifications on stdout."""
    fs = RealFilesystem()
    cfg = ProjectCodingConfig(
        workspace=tmp_path,
        filesystem=fs,
        completer=_offline_write_stub(),  # type: ignore[arg-type]
    )
    injector = get_injector(cfg)
    gen = injector.inject(DurableGraphGenerator)
    # Point file store at tmp so tests don't share process MCP state.
    from mechaharness.durable_graph_generator import FileGeneratorRunStore

    gen._runs = FileGeneratorRunStore(tmp_path / "runs.json")  # noqa: SLF001

    stdin = io.BytesIO()
    stdout = io.BytesIO()
    server = GeneratorMcpServer(gen, stdin=stdin, stdout=stdout, framing="ndjson")

    def send(obj: dict) -> None:
        stdin.write(json.dumps(obj).encode("utf-8") + b"\n")

    send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "generator_start",
                "arguments": {
                    "recipe_id": "guided_coding",
                    "run_id": "prog-1",
                    "controller_id": "unit",
                    "inputs": {"goal": "write stub"},
                },
                "_meta": {"progressToken": "p-start"},
            },
        }
    )
    stdin.seek(0)
    server.serve_forever()

    lines = [json.loads(ln) for ln in stdout.getvalue().split(b"\n") if ln.strip()]
    progress = [m for m in lines if m.get("method") == "notifications/progress"]
    results = [m for m in lines if m.get("id") == 1]
    assert progress
    assert progress[0]["params"]["progressToken"] == "p-start"
    assert any("guided_coding" in (p["params"].get("message") or "") for p in progress)
    assert results and results[0]["result"]["structuredContent"]["kind"] == (
        "advice_requested"
    )

    # Resume with progress: offline stub writes a file through local work.
    stdin2 = io.BytesIO()
    stdout2 = io.BytesIO()
    server2 = GeneratorMcpServer(gen, stdin=stdin2, stdout=stdout2, framing="ndjson")
    y1 = results[0]["result"]["structuredContent"]

    def send2(obj: dict) -> None:
        stdin2.write(json.dumps(obj).encode("utf-8") + b"\n")

    send2(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "generator_resume",
                "arguments": {
                    "run_id": "prog-1",
                    "expected_sequence": y1["sequence"],
                    "request_id": y1["request_id"],
                    "choice_id": "minimal",
                    "controller_id": "unit",
                    "idempotency_key": "prog-1:1",
                },
                "_meta": {"progressToken": "p-resume"},
            },
        }
    )
    stdin2.seek(0)
    server2.serve_forever()
    lines2 = [json.loads(ln) for ln in stdout2.getvalue().split(b"\n") if ln.strip()]
    progress2 = [m for m in lines2 if m.get("method") == "notifications/progress"]
    assert progress2
    messages = [p["params"].get("message") or "" for p in progress2]
    assert any("work_item 1" in m for m in messages)
    assert any("tool_round" in m for m in messages)
    done = next(m for m in lines2 if m.get("id") == 2)
    assert done["result"]["structuredContent"]["kind"] == "completed"
