"""Append-only timing / trace lines for suite runs and coding bursts.

Writes JSONL next to the coding workspace (``…/suite_runs/<id>/TIMING.jsonl``)
so live dogfood can answer "where did the hours go?" without a second bus.
Not a warehouse schema — host EventLog remains the product observability path.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def timing_log_path(workspace_root: str | Path | None) -> Path | None:
    """``<suite_run_root>/TIMING.jsonl`` when *workspace_root* is a suite workspace."""
    if workspace_root is None:
        return None
    root = Path(workspace_root).expanduser().resolve()
    return root.parent / "TIMING.jsonl"


def append_timing(
    workspace_root: str | Path | None,
    *,
    kind: str,
    elapsed_s: float | None = None,
    **fields: Any,
) -> dict[str, Any] | None:
    """Append one JSON object to the suite timing log; return the record."""
    path = timing_log_path(workspace_root)
    if path is None:
        return None
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": str(kind),
        **{k: v for k, v in fields.items() if v is not None},
    }
    if elapsed_s is not None:
        record["elapsed_s"] = round(float(elapsed_s), 3)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        return record
    return record


def announce_timing(line: str) -> None:
    """Print a timing line (visible with ``pytest -s``)."""
    sys.stdout.write(line if line.endswith("\n") else line + "\n")
    sys.stdout.flush()


class TimingSpan:
    """Wall-clock span that appends on ``end()``."""

    def __init__(
        self,
        workspace_root: str | Path | None,
        *,
        kind: str,
        **fields: Any,
    ) -> None:
        self._workspace_root = workspace_root
        self._kind = kind
        self._fields = dict(fields)
        self._t0 = time.perf_counter()
        self.elapsed_s: float | None = None
        self.record: dict[str, Any] | None = None

    def end(self, **extra: Any) -> dict[str, Any] | None:
        self.elapsed_s = time.perf_counter() - self._t0
        merged = {**self._fields, **extra}
        self.record = append_timing(
            self._workspace_root,
            kind=self._kind,
            elapsed_s=self.elapsed_s,
            **merged,
        )
        return self.record


def inference_budget_fields() -> dict[str, Any]:
    """Env knobs that dominate live wall-clock (not Settings)."""
    out: dict[str, Any] = {}
    for key in (
        "MECHA_INFERENCE_TIMEOUT_SECONDS",
        "MECHA_HTTP_TIMEOUT_SECONDS",
        "MECHA_CODING_MAX_ITERATIONS",
        "MECHA_MAX_TOKENS",
        "MECHA_MODEL",
        "MECHA_STORY_BACKEND",
    ):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            out[key] = raw
    return out


__all__ = [
    "TimingSpan",
    "announce_timing",
    "append_timing",
    "inference_budget_fields",
    "timing_log_path",
]
