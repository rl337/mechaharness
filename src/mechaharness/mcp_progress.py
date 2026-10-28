"""MCP ``notifications/progress`` helpers for long generator tool calls.

The client supplies ``progressToken`` on ``tools/call`` ``_meta``. We echo it
and put a human path in ``message``::

    guided_coding › plan_tile › work_item 4 › tool_round 3 › write_file

See MCP Progress utility and Cursor's idle-timeout reset on progress.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

ProgressWriter = Callable[[dict[str, Any]], None]

_active: ContextVar[McpProgressReporter | None] = ContextVar(
    "mechaharness_mcp_progress", default=None
)

PATH_SEP = " › "


def format_progress_path(segments: Sequence[str]) -> str:
    """Join non-empty path segments with the recipe-chain separator."""
    parts = [str(s).strip() for s in segments if str(s).strip()]
    return PATH_SEP.join(parts)


def coding_progress_prefix(recipe_id: str) -> list[str]:
    """Root segments for project-coding local work under a generator recipe."""
    rid = str(recipe_id or "").strip() or "recipe"
    if rid == "guided_coding":
        return [rid, "plan_tile"]
    return [rid]


@dataclass
class McpProgressReporter:
    """Emit monotonic MCP progress notifications for one open ``tools/call``."""

    progress_token: str | int
    write: ProgressWriter
    base_segments: list[str] = field(default_factory=list)
    _progress: int = 0

    def report(
        self,
        *segments: str,
        message: str | None = None,
        total: float | None = None,
    ) -> None:
        """Send ``notifications/progress`` (no JSON-RPC id)."""
        self._progress += 1
        path = format_progress_path([*self.base_segments, *segments])
        text = message if message is not None else path
        if message is not None and path and message != path:
            text = f"{path} — {message}"
        params: dict[str, Any] = {
            "progressToken": self.progress_token,
            "progress": float(self._progress),
            "message": text or "working…",
        }
        if total is not None:
            params["total"] = float(total)
        self.write(
            {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": params,
            }
        )

    def extend_base(self, *segments: str) -> None:
        """Append sticky path prefix for subsequent reports."""
        for seg in segments:
            s = str(seg).strip()
            if s:
                self.base_segments.append(s)


def get_mcp_progress() -> McpProgressReporter | None:
    """Return the reporter bound for the current MCP ``tools/call``, if any."""
    return _active.get()


def report_mcp_progress(*segments: str, message: str | None = None) -> None:
    """No-op when no MCP progress context is active."""
    reporter = get_mcp_progress()
    if reporter is not None:
        reporter.report(*segments, message=message)


@contextmanager
def mcp_progress_scope(
    progress_token: str | int | None,
    write: ProgressWriter,
    *,
    base_segments: Sequence[str] | None = None,
) -> Iterator[McpProgressReporter | None]:
    """Bind a reporter for the duration of one ``tools/call`` (token optional)."""
    if progress_token is None or progress_token == "":
        token = _active.set(None)
        try:
            yield None
        finally:
            _active.reset(token)
        return
    reporter = McpProgressReporter(
        progress_token=progress_token,
        write=write,
        base_segments=list(base_segments or ()),
    )
    token = _active.set(reporter)
    try:
        yield reporter
    finally:
        _active.reset(token)


def extract_progress_token(params: dict[str, Any]) -> str | int | None:
    """Read ``_meta.progressToken`` from an MCP ``tools/call`` params object."""
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("progressToken")
    if isinstance(raw, (str, int)) and not isinstance(raw, bool):
        return raw
    return None


__all__ = [
    "McpProgressReporter",
    "PATH_SEP",
    "coding_progress_prefix",
    "extract_progress_token",
    "format_progress_path",
    "get_mcp_progress",
    "mcp_progress_scope",
    "report_mcp_progress",
]
