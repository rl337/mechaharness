"""Private Git checkout and review artifacts for a durable coding handoff."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from tempfile import gettempdir, mkdtemp
from typing import Any

from mechaharness.durable_graph_generator import GeneratorRunRecord
from mechaharness.generator_local_work import GeneratorLocalWork, ProjectCodingLocalWork
from mechaharness.isolation.workspace_isolation import (
    WorkspaceIsolationHandle,
    WorkspaceIsolationProvider,
    WorkspaceIsolationRequest,
)


def _git(root: Path, *args: str, index: Path | None = None) -> bytes:
    env = os.environ.copy()
    # An inherited worktree or index must never redirect writes to the host.
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(name, None)
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    if index:
        env["GIT_INDEX_FILE"] = str(index)
    return subprocess.check_output(["git", "-C", str(root), *args], env=env, stderr=subprocess.PIPE)


def _tree(root: Path) -> str:
    index = root.parent / "review.index"
    _git(root, "add", "-A", "--", ".", index=index)
    return _git(root, "write-tree", index=index).decode().strip()


class CodingRepositoryIsolation(WorkspaceIsolationProvider):
    """Copy the caller's tracked and non-ignored files into an independent clone."""

    def __init__(self, source: Path) -> None:
        self.source = source.resolve()

    def acquire(self, request: WorkspaceIsolationRequest) -> WorkspaceIsolationHandle:
        directory = Path(mkdtemp(prefix="mecha-coding-"))
        root = directory / "checkout"
        try:
            revision = None
            if (self.source / ".git").exists():
                _git(
                    self.source,
                    "clone",
                    "--local",
                    "--no-hardlinks",
                    "--no-checkout",
                    "--",
                    str(self.source),
                    str(root),
                )
                _git(root, "remote", "remove", "origin")
                try:
                    revision = _git(root, "rev-parse", "--verify", "HEAD").decode().strip()
                except subprocess.CalledProcessError as exc:
                    if exc.returncode != 128:
                        raise
                if revision:
                    _git(root, "reset", "--mixed", "HEAD")
                    _git(root, "read-tree", "HEAD", index=directory / "review.index")
                names = _git(
                    self.source, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
                )
            else:
                root.mkdir()
                _git(root, "init", "--quiet")
                names = _git(
                    self.source,
                    f"--git-dir={root / '.git'}",
                    f"--work-tree={self.source}",
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "-z",
                )
            for raw in set(names.split(b"\0")):
                if not raw:
                    continue
                name = Path(os.fsdecode(raw))
                src = self.source / name
                target = root / name
                if src.parent.resolve() != src.parent:
                    raise ValueError(f"symlinked repository directory: {name}")
                if src.is_symlink():
                    link = os.readlink(src)
                    if os.path.isabs(link) or not src.resolve().is_relative_to(self.source):
                        raise ValueError(f"link escapes coding workspace: {name}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(link)
                elif src.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target)
                elif src.is_dir():
                    raise ValueError(
                        f"nested repositories require a host workspace provider: {name}"
                    )
            baseline = _tree(root)
            return WorkspaceIsolationHandle(
                label=request.label,
                provider_kind="git_clone",
                root_ref=str(root),
                metadata={"base_tree": baseline, "base_revision": revision},
            )
        except BaseException:
            shutil.rmtree(directory)
            raise

    def release(self, handle: WorkspaceIsolationHandle) -> None:
        if handle.root_ref:
            root = Path(handle.root_ref).resolve()
            if (
                root.name != "checkout"
                or not root.parent.name.startswith("mecha-coding-")
                or root.parent.parent != Path(gettempdir()).resolve()
            ):
                raise ValueError("invalid private coding workspace")
            shutil.rmtree(root.parent)

    @staticmethod
    def checkpoint(root: Path) -> str:
        return _tree(root)

    @staticmethod
    def rewind(root: Path, tree: str) -> None:
        # The private review index must see newly created paths for read-tree
        # to remove them. The caller's Git index is never touched.
        _tree(root)
        _git(root, "read-tree", "--reset", "-u", tree, index=root.parent / "review.index")

    def review(self, handle: WorkspaceIsolationHandle) -> dict[str, Any]:
        assert handle.root_ref is not None
        root = Path(handle.root_ref)
        updated = _tree(root)
        baseline = handle.metadata["base_tree"]
        names = _git(root, "diff", "--name-only", "-z", baseline, updated)
        patch = root.parent / "changes.patch"
        pending = patch.with_suffix(".tmp")
        pending.write_bytes(_git(root, "diff", "--binary", "--no-ext-diff", baseline, updated))
        pending.replace(patch)
        return {
            **handle.metadata,
            "workspace_root": str(root),
            "patch_path": str(patch),
            "written_files": [os.fsdecode(name) for name in names.split(b"\0") if name],
        }


class RepositoryCodingLocalWork(GeneratorLocalWork):
    def __init__(
        self,
        provider: CodingRepositoryIsolation,
        make_worker: Callable[[Path], GeneratorLocalWork],
    ) -> None:
        self.provider = provider
        self.make_worker = make_worker

    def run(self, record: GeneratorRunRecord) -> dict[str, Any]:
        try:
            saved = record.coding_checkout
            if saved:
                handle = WorkspaceIsolationHandle.model_validate(saved)
            else:
                handle = self.provider.acquire(WorkspaceIsolationRequest(label=record.run_id))
                record.coding_checkout = handle.model_dump()
            assert handle.root_ref is not None
            root = Path(handle.root_ref)
            worker = self.make_worker(root)
            if isinstance(worker, ProjectCodingLocalWork):
                before = self.provider.checkpoint(root)
                worker.bind_workspace_recovery(lambda: self.provider.rewind(root, before))
            result = worker.run(record)
            review = self.provider.review(handle)
            patch = review["patch_path"]
            if patch not in record.artifact_refs:
                record.artifact_refs.append(patch)
            return {**result, **review}
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return {"result": "failed", "error": f"coding workspace: {exc}"}
