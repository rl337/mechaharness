"""Refuse catastrophic overwrites from coding-delegate ``write_file``.

Local Completers sometimes "gut" an existing module — replace a large file
with a tiny broken stub. :class:`CodingWriteGuard` blocks that at the tool
boundary before the filesystem changes stick.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingWriteGuard:
    """Policy for overwriting existing workspace files.

    Defaults match the observed failure mode: an existing multi-kilobyte
    ``.py`` file replaced by a handful of lines that no longer parse or retain
    prior top-level definitions.
    """

    # New content must be at least this fraction of the prior byte length when
    # the existing file is at least ``min_existing_bytes`` long.
    min_retain_ratio: float = 0.35
    min_existing_bytes: int = 512
    # Absolute floor for replacements of large files (bytes).
    min_replacement_bytes: int = 200
    # When True, ``*.py`` replacements must ``ast.parse``.
    require_python_parse: bool = True
    # When True, refuse if every prior top-level def/class name disappears.
    require_retain_some_defs: bool = True

    def check(
        self,
        *,
        path: str | Path,
        existing: str | None,
        new_content: str,
    ) -> str | None:
        """Return an error message if the write should be refused, else ``None``."""
        text = new_content if new_content is not None else ""
        rel = str(path)
        suffix = Path(rel).suffix.lower()

        if existing is None:
            if suffix == ".py" and self.require_python_parse:
                return _python_parse_error(rel, text)
            return None

        old = existing
        old_len = len(old.encode("utf-8"))
        new_len = len(text.encode("utf-8"))

        if old_len >= self.min_existing_bytes:
            if new_len < self.min_replacement_bytes:
                return (
                    f"refused write to {rel}: replacement too small "
                    f"({new_len} bytes < {self.min_replacement_bytes}; "
                    f"existing was {old_len} bytes) — looks like file gutting"
                )
            min_keep = int(old_len * float(self.min_retain_ratio))
            if new_len < min_keep:
                return (
                    f"refused write to {rel}: replacement retains "
                    f"{new_len}/{old_len} bytes "
                    f"(<{self.min_retain_ratio:.0%} of existing) — "
                    f"looks like file gutting"
                )

        if suffix == ".py" and self.require_python_parse:
            err = _python_parse_error(rel, text)
            if err:
                return err

        if (
            suffix == ".py"
            and self.require_retain_some_defs
            and old_len >= self.min_existing_bytes
        ):
            old_defs = _top_level_defs(old)
            new_defs = _top_level_defs(text)
            if old_defs and not (old_defs & new_defs):
                sample = ", ".join(sorted(old_defs)[:8])
                return (
                    f"refused write to {rel}: dropped all prior top-level "
                    f"defs/classes ({sample}) — looks like file gutting"
                )
        return None


def _python_parse_error(rel: str, text: str) -> str | None:
    try:
        ast.parse(text, filename=rel)
    except SyntaxError as exc:
        return f"refused write to {rel}: Python syntax error: {exc}"
    return None


def _top_level_defs(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


DEFAULT_CODING_WRITE_GUARD = CodingWriteGuard()

__all__ = ["CodingWriteGuard", "DEFAULT_CODING_WRITE_GUARD"]
