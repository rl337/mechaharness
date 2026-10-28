"""Unit tests for injectable CodingGit backends."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mechaharness.coding_git import (
    CodingGitResult,
    LocalGitHttpPullRequestCodingGit,
    LocalProcessCodingGit,
    RecordingPullRequestCodingGit,
)
from mechaharness.github_client import GitHubClient
from mechaharness.github_connection import GitHubConnectionConfig


def test_recording_pull_request_uses_local_git_and_mocks_forge(tmp_path: Path) -> None:
    root = tmp_path
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True
    )
    (root / "a.txt").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "change"], cwd=root, check=True, capture_output=True
    )

    inner = LocalProcessCodingGit(workspace=root)
    git = RecordingPullRequestCodingGit(inner, pr_url="https://example.test/pull/9")
    assert git.status().ok
    assert git.log(base="HEAD~1").ok
    assert "change" in git.log(base="HEAD~1").stdout
    assert git.diff(base="HEAD~1").ok

    pr = git.create_pull_request(
        title="Ship change", body="## Summary\n- change\n", base="main"
    )
    assert pr.ok
    assert "example.test/pull/9" in pr.stdout
    assert len(git.created) == 1
    assert git.created[0]["title"] == "Ship change"
    assert git.created[0]["base"] == "main"


def test_local_git_http_pull_request_coding_git(tmp_path: Path) -> None:
    root = tmp_path
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "checkout", "-b", "feature"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:acme/demo.git"],
        cwd=root,
        check=True,
        capture_output=True,
    )

    class _FakeForge(GitHubClient):
        def create_pull_request(
            self,
            *,
            owner: str,
            repo: str,
            title: str,
            body: str,
            head: str,
            base: str = "main",
            draft: bool = False,
        ) -> CodingGitResult:
            del body, draft
            return CodingGitResult(
                ok=True,
                stdout="https://github.com/acme/demo/pull/3\n",
                extra={
                    "owner": owner,
                    "repo": repo,
                    "title": title,
                    "head": head,
                    "base": base,
                },
            )

        def list_check_runs(
            self, *, owner: str, repo: str, ref: str
        ) -> CodingGitResult:
            del owner, repo, ref
            return CodingGitResult(ok=False, error="unused")

        def get_workflow_job_logs(
            self,
            *,
            owner: str,
            repo: str,
            job_id: int | str,
            max_bytes: int = 120_000,
        ) -> CodingGitResult:
            del owner, repo, job_id, max_bytes
            return CodingGitResult(ok=False, error="unused")

    git = LocalGitHttpPullRequestCodingGit(
        workspace=root,
        github=_FakeForge(),
        connection=GitHubConnectionConfig(token="x"),
    )
    pr = git.create_pull_request(title="Add feature", body="body", base="main")
    assert pr.ok
    assert "pull/3" in pr.stdout
    assert pr.extra["owner"] == "acme"
    assert pr.extra["repo"] == "demo"
    assert pr.extra["head"] == "feature"
