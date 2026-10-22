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
