"""Injectable VCS + PR surface for project-coding / guided_coding tools.

Hosts bind a :class:`CodingGit` via ``ProjectCodingConfig.get_coding_git()``.
Default is :class:`LocalProcessCodingGit` (local ``git`` / ``gh``, SSH agent).
Alternate transports (HTTPS + token, host API wrappers) implement the same ABC
without changing tool names or the guided_coding recipe.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mechaharness.github_client import GitHubClient
    from mechaharness.github_connection import GitHubConnectionConfig

# Branch/tag + relative history (HEAD~1); block shell metacharacters.
_SAFE_REF = re.compile(r"^[A-Za-z0-9._/\-~^]+$")
_SAFE_REMOTE = re.compile(r"^[A-Za-z0-9._\-]+$")


def validate_git_ref(value: str, *, label: str = "ref") -> str:
    """Return *value* if it is a safe ref name; else raise ``ValueError``."""
    text = (value or "").strip()
    if not text or not _SAFE_REF.match(text):
        raise ValueError(f"unsafe {label}: {value!r}")
    return text


def validate_git_remote(value: str) -> str:
    """Return *value* if it is a safe remote name; else raise ``ValueError``."""
    text = (value or "origin").strip() or "origin"
    if not _SAFE_REMOTE.match(text):
        raise ValueError(f"unsafe remote: {value!r}")
    return text


@dataclass(frozen=True)
class CodingGitResult:
    """Structured outcome for a CodingGit operation (tool layer JSON-serializes)."""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_tool_json(self) -> str:
        """Serialize for tool-handler return values."""
        payload = asdict(self)
        if not payload["extra"]:
            del payload["extra"]
        if payload["error"] is None:
            del payload["error"]
        return json.dumps(payload)


class CodingGit(ABC):
    """Workspace-scoped version control + pull-request operations.

    Tool names stay stable (``git_status``, ``git_diff``, …); only this binding
    changes. Implement HTTPS / PAT / forge-API backends as additional subclasses.
    """

    @abstractmethod
    def status(self) -> CodingGitResult:
        """Short working-tree / branch status."""

    @abstractmethod
    def log(self, *, base: str = "origin/main", max_count: int = 40) -> CodingGitResult:
        """Commits on HEAD not in *base* (``base..HEAD``)."""

    @abstractmethod
    def diff(
        self,
        *,
        base: str = "origin/main",
        stat_only: bool = True,
        max_bytes: int = 120_000,
    ) -> CodingGitResult:
        """Diff ``base...HEAD`` (triple-dot merge-base form)."""

    @abstractmethod
    def push(
        self, *, remote: str = "origin", set_upstream: bool = True
    ) -> CodingGitResult:
        """Publish current HEAD to *remote*."""

    @abstractmethod
    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        base: str = "main",
        draft: bool = False,
    ) -> CodingGitResult:
        """Open a pull request against *base* with *title* / *body*."""


class RecordingPullRequestCodingGit(CodingGit):
    """Delegate VCS ops to *inner*; record PRs instead of calling a forge.

    Story / CI default when local ``git`` is fine but GitHub must stay mocked
    (no ``gh auth``, no network). ``created`` holds each
    ``create_pull_request`` call for assertions.
    """

    def __init__(
        self,
        inner: CodingGit,
        *,
        pr_url: str = "https://example.test/pull/1",
    ) -> None:
        self._inner = inner
        self._pr_url = str(pr_url)
        self.created: list[dict[str, Any]] = []

    def status(self) -> CodingGitResult:
        return self._inner.status()

    def log(self, *, base: str = "origin/main", max_count: int = 40) -> CodingGitResult:
        return self._inner.log(base=base, max_count=max_count)

    def diff(
        self,
        *,
        base: str = "origin/main",
        stat_only: bool = True,
        max_bytes: int = 120_000,
    ) -> CodingGitResult:
        return self._inner.diff(
            base=base, stat_only=stat_only, max_bytes=max_bytes
        )

    def push(
        self, *, remote: str = "origin", set_upstream: bool = True
    ) -> CodingGitResult:
        return self._inner.push(remote=remote, set_upstream=set_upstream)

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        base: str = "main",
        draft: bool = False,
    ) -> CodingGitResult:
        title_text = (title or "").strip()
        if not title_text:
            return CodingGitResult(ok=False, error="title required")
        record = {
            "title": title_text,
            "body": body if body is not None else "",
            "base": base,
            "draft": bool(draft),
            "url": self._pr_url,
        }
        self.created.append(record)
        return CodingGitResult(
            ok=True,
            returncode=0,
            stdout=f"{self._pr_url}\n",
            extra={"title": title_text, "base": base, "draft": bool(draft)},
        )


class LocalProcessCodingGit(CodingGit):
    """Default: invoke local ``git`` and ``gh`` with ``cwd=workspace``.

    Uses the operator environment (SSH agent, ``~/.gitconfig``, ``gh`` auth).
    Prefer this for interactive MCP dogfood on a developer machine.
    """

    def __init__(
        self,
        *,
        workspace: Path | str,
        git_executable: str | None = None,
        gh_executable: str | None = None,
    ) -> None:
        self._root = Path(workspace).expanduser().resolve()
        self._git = git_executable or "git"
        self._gh = gh_executable or _resolve_gh()

    def status(self) -> CodingGitResult:
        return self._run([self._git, "status", "-sb"])

    def log(self, *, base: str = "origin/main", max_count: int = 40) -> CodingGitResult:
        try:
            ref = validate_git_ref(base, label="base")
        except ValueError as exc:
            return CodingGitResult(ok=False, error=str(exc))
        count = max(1, min(int(max_count), 200))
        return self._run(
            [self._git, "log", "--oneline", f"{ref}..HEAD", f"-{count}"]
        )

    def diff(
        self,
        *,
        base: str = "origin/main",
        stat_only: bool = True,
        max_bytes: int = 120_000,
    ) -> CodingGitResult:
        try:
            ref = validate_git_ref(base, label="base")
        except ValueError as exc:
            return CodingGitResult(ok=False, error=str(exc))
        cmd = [self._git, "diff"]
        if bool(stat_only):
            cmd.append("--stat")
        cmd.append(f"{ref}...HEAD")
        return self._run(cmd, max_stdout=max(4_000, int(max_bytes)))

    def push(
        self, *, remote: str = "origin", set_upstream: bool = True
    ) -> CodingGitResult:
        try:
            rem = validate_git_remote(remote)
        except ValueError as exc:
            return CodingGitResult(ok=False, error=str(exc))
        cmd = [self._git, "push"]
        if bool(set_upstream):
            cmd.append("-u")
        cmd.extend([rem, "HEAD"])
        return self._run(cmd, timeout=120)

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        base: str = "main",
        draft: bool = False,
    ) -> CodingGitResult:
        try:
            base_ref = validate_git_ref(base, label="base")
        except ValueError as exc:
            return CodingGitResult(ok=False, error=str(exc))
        title_text = (title or "").strip()
        if not title_text:
            return CodingGitResult(ok=False, error="title required")
        body_dir = self._root / ".mechaharness"
        body_dir.mkdir(parents=True, exist_ok=True)
        body_path = body_dir / "pr_body.md"
        body_path.write_text(body if body is not None else "", encoding="utf-8")
        cmd = [
            self._gh,
            "pr",
            "create",
            "--base",
            base_ref,
            "--title",
            title_text,
            "--body-file",
            str(body_path),
        ]
        if bool(draft):
            cmd.append("--draft")
        return self._run(cmd, timeout=120)

    def _run(
        self,
        command: list[str],
        *,
        timeout: float = 300,
        max_stdout: int = 8000,
        max_stderr: int = 4000,
    ) -> CodingGitResult:
        try:
            completed = subprocess.run(
                command,
                cwd=str(self._root),
                shell=False,
                capture_output=True,
                text=True,
                timeout=float(timeout),
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            return CodingGitResult(ok=False, error=str(exc))
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        return CodingGitResult(
            ok=completed.returncode == 0,
            returncode=int(completed.returncode),
            stdout=stdout[-int(max_stdout) :],
            stderr=stderr[-int(max_stderr) :],
        )


def _resolve_gh() -> str:
    found = shutil.which("gh")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "gh"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return "gh"


class LocalGitHttpPullRequestCodingGit(CodingGit):
    """Local ``git`` for VCS; injectable :class:`GitHubClient` for pull requests.

    Prefer this over ``gh`` when ``GitHubConnectionConfig`` has a token.
    """

    def __init__(
        self,
        *,
        workspace: Path | str,
        github: GitHubClient,
        connection: GitHubConnectionConfig | None = None,
        git_executable: str | None = None,
    ) -> None:
        self._vcs = LocalProcessCodingGit(
            workspace=workspace, git_executable=git_executable
        )
        self._github = github
        self._connection = connection

    def status(self) -> CodingGitResult:
        return self._vcs.status()

    def log(self, *, base: str = "origin/main", max_count: int = 40) -> CodingGitResult:
        return self._vcs.log(base=base, max_count=max_count)

    def diff(
        self,
        *,
        base: str = "origin/main",
        stat_only: bool = True,
        max_bytes: int = 120_000,
    ) -> CodingGitResult:
        return self._vcs.diff(base=base, stat_only=stat_only, max_bytes=max_bytes)

    def push(
        self, *, remote: str = "origin", set_upstream: bool = True
    ) -> CodingGitResult:
        return self._vcs.push(remote=remote, set_upstream=set_upstream)

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        base: str = "main",
        draft: bool = False,
    ) -> CodingGitResult:
        head_out = self._vcs._run(  # noqa: SLF001 - shared process helper
            ["git", "rev-parse", "--abbrev-ref", "HEAD"]
        )
        if not head_out.ok:
            return CodingGitResult(
                ok=False,
                error=head_out.error or head_out.stderr or "could not resolve HEAD",
            )
        head = head_out.stdout.strip()
        owner = (self._connection.owner if self._connection else None) or None
        repo = (self._connection.repo if self._connection else None) or None
        if not owner or not repo:
            remote_out = self._vcs._run(  # noqa: SLF001
                ["git", "remote", "get-url", "origin"]
            )
            if not remote_out.ok:
                return CodingGitResult(
                    ok=False,
                    error=(
                        remote_out.error
                        or remote_out.stderr
                        or "could not read origin remote"
                    ),
                )
            from mechaharness.github_client import parse_github_owner_repo

            parsed = parse_github_owner_repo(remote_out.stdout.strip())
            if parsed is None:
                return CodingGitResult(
                    ok=False, error="could not parse owner/repo from origin URL"
                )
            owner, repo = parsed
        return self._github.create_pull_request(
            owner=owner,
            repo=repo,
            title=title,
            body=body,
            head=head,
            base=base,
            draft=draft,
        )


__all__ = [
    "CodingGit",
    "CodingGitResult",
    "LocalProcessCodingGit",
    "RecordingPullRequestCodingGit",
    "LocalGitHttpPullRequestCodingGit",
    "validate_git_ref",
    "validate_git_remote",
]
