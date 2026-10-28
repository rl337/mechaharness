"""Filesystem checkpoints of a coding workspace for escalate / suite handoff.

Copies every file under the workspace into a sibling directory keyed by the
workspace path. Suite runners refresh this after each successful stage so
restore never rewinds to an empty pre-010 tree. Coding local work refreshes at
burst start (and on success) so mid-stage escalate undoes trash writes only.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def coding_workspace_checkpoint_dir(workspace_root: str | Path) -> Path:
    """Sibling dir for the checkpoint of *workspace_root*."""
    root = Path(workspace_root).expanduser().resolve()
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    return root.parent / f".mechaharness_coding_ws_checkpoint_{digest}"


def _iter_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


def save_coding_workspace_checkpoint(workspace_root: str | Path) -> Path:
    """Overwrite the checkpoint with the current workspace file tree.

    Always replaces a prior checkpoint so suite stage success and coding bursts
    advance the restore baseline. Returns the checkpoint directory.
    """
    src = Path(workspace_root).expanduser().resolve()
    dest = coding_workspace_checkpoint_dir(src)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if not src.is_dir():
        return dest
    for path in _iter_files(src):
        rel = path.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return dest


def restore_coding_workspace_checkpoint(workspace_root: str | Path) -> bool:
    """Replace workspace contents from the checkpoint.

    Returns ``False`` when there is no checkpoint, or when the checkpoint is
    empty while the workspace still has files (refuses to gut a good tree).
    """
    dest = Path(workspace_root).expanduser().resolve()
    src = coding_workspace_checkpoint_dir(dest)
    if not src.is_dir():
        return False
    ck_files = _iter_files(src)
    ws_files = _iter_files(dest) if dest.is_dir() else []
    if not ck_files and ws_files:
        return False
    dest.mkdir(parents=True, exist_ok=True)
    for path in _iter_files(dest):
        path.unlink()
    for path in ck_files:
        rel = path.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return True


__all__ = [
    "coding_workspace_checkpoint_dir",
    "restore_coding_workspace_checkpoint",
    "save_coding_workspace_checkpoint",
]
