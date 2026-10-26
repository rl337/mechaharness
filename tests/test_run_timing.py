"""Suite / coding TIMING.jsonl helpers."""

from __future__ import annotations

import json
from pathlib import Path

from mechaharness.run_timing import (
    TimingSpan,
    append_timing,
    timing_log_path,
)


def test_append_timing_writes_jsonl_beside_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    path = timing_log_path(ws)
    assert path == tmp_path / "TIMING.jsonl"
    append_timing(ws, kind="suite_stage", stage="a/b", status="ok", elapsed_s=1.25)
    span = TimingSpan(ws, kind="coding_work_item", item_id="t1")
    span.end(result="ok")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["kind"] == "suite_stage"
    assert first["elapsed_s"] == 1.25
    second = json.loads(lines[1])
    assert second["kind"] == "coding_work_item"
    assert second["result"] == "ok"
    assert "elapsed_s" in second


def test_append_timing_noop_without_workspace() -> None:
    assert append_timing(None, kind="x") is None
