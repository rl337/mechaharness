"""Checkpoint and undo coding edits with explicit file ownership."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from mechaharness.file_lock import file_lock
from mechaharness.project_coding_tools import WorkspacePaths


def coding_workspace_checkpoint_dir(workspace_root: str | Path) -> Path:
    root = Path(workspace_root).expanduser().resolve()
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    return root.parent / f".mechaharness_coding_ws_checkpoint_{digest}"


def save_coding_workspace_checkpoint(workspace_root: str | Path) -> Path:
    """Save the current baseline for sequential suite handoff."""
    root = Path(workspace_root).resolve()
    dest = coding_workspace_checkpoint_dir(root)
    with file_lock(dest.with_suffix(".lock")), TemporaryDirectory(dir=dest.parent) as directory:
        staged = Path(directory) / "new"
        staged.mkdir()
        if root.exists():
            for current, dirs, names in os.walk(root):
                parent = Path(current)
                dirs[:] = [d for d in dirs if d != ".git" and not (parent / d).is_symlink()]
                for name in names:
                    path = parent / name
                    if path.is_symlink() or not path.is_file():
                        continue
                    target = staged / path.relative_to(root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
        previous = dest.with_suffix(".previous")
        if dest.exists():
            if previous.exists():
                shutil.rmtree(previous)
            dest.rename(previous)
        try:
            staged.rename(dest)
        except OSError:
            if previous.exists() and not dest.exists():
                previous.rename(dest)
            raise
        if previous.exists():
            shutil.rmtree(previous)
    return dest


def restore_edit(path: Path, before: bytes | None, written: bytes | None) -> bool:
    """Undo exactly one known write while preserving a later editor's version."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return False
    current = path.read_bytes() if path.exists() else None
    if current != written:
        return False
    if before == current:
        return True
    if before is None:
        path.unlink()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            tmp.write(before)
        replacement = Path(tmp.name)
        try:
            if path.exists():
                shutil.copymode(path, replacement)
            replacement.replace(path)
        finally:
            replacement.unlink(missing_ok=True)
    return True


def restore_coding_workspace_checkpoint(
    workspace_root: str | Path, *, writes: Mapping[str, bytes] | None = None
) -> bool:
    """Restore only supplied agent writes whose current bytes still match."""
    root = WorkspacePaths(workspace_root)
    snapshot = coding_workspace_checkpoint_dir(root.root)
    if not writes:
        return False
    with file_lock(snapshot.with_suffix(".lock")):
        if not snapshot.is_dir():
            # Recover the last complete snapshot if the saving process exited
            # between the two renames.
            snapshot = snapshot.with_suffix(".previous")
        if not snapshot.is_dir():
            return False
        restored = True
        for name, written in writes.items():
            path = root.resolve(name)
            if root.root / name != path:
                restored = False
                continue
            original = snapshot / path.relative_to(root.root)
            before = original.read_bytes() if original.is_file() else None
            if not restore_edit(path, before, written):
                restored = False
        return restored
