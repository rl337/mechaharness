"""Unit tests for injectable CodingGit backends."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mechaharness.coding_git import (
    LocalProcessCodingGit,
    RecordingPullRequestCodingGit,
)


def test_recording_pull_request_uses_local_git_and_mocks_forge(tmp_path: Path) -> None:
    root = tmp_path
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
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
