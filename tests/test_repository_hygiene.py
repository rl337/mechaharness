"""Redacted hygiene findings distinguish local artifacts from tracked examples."""

from __future__ import annotations

import pytest

from scripts.repository_hygiene import content_issues, path_issue


@pytest.mark.parametrize(
    "path,forbidden",
    [
        (".env", True),
        (".env/env.sh", True),
        (".env.production", True),
        (".env.example", False),
        ("docs/guides/codex-mcp.config.toml.example", False),
        ("docs/plans/private.md", True),
        ("dist/package.whl", True),
        ("tests/__pycache__/test.cpython-312.pyc", True),
        (".cursor/mcp.json", True),
        (".cursor/skills/project-docs/SKILL.md", False),
        ("tests/fixtures/models/example.json", False),
        ("src/package.egg-info/PKG-INFO", True),
        ("docs/package.egg-info-notes.md", False),
    ],
)
def test_local_artifact_paths(path: str, forbidden: bool) -> None:
    assert (path_issue(path) is not None) == forbidden


@pytest.mark.parametrize(
    "value,category",
    [
        ("sk-proj-" + "a" * 40, "OpenAI project key"),
        ("ghp_" + "a" * 40, "GitHub token"),
        ("AKIA" + "A" * 16, "AWS access key"),
        ("-----BEGIN " + "PRIVATE KEY-----", "private key"),
        ("/Users" + "/example/workspace", "absolute home path"),
        ("192." + "168.1.2", "private endpoint"),
    ],
)
def test_sensitive_findings_never_echo_values(value: str, category: str) -> None:
    findings = content_issues("example.txt", ("heading\n" + value).encode())
    assert findings == [f"example.txt:2: {category}"]
    assert value not in "\n".join(findings)


def test_placeholders_and_loopback_examples_are_allowed() -> None:
    assert content_issues("example.md", b"sk-... http://127.0.0.1:8000 /ABS/PATH/project") == []


def test_finding_escapes_control_characters_in_filenames() -> None:
    secret = ("ghp_" + "a" * 40).encode()
    assert content_issues("notes\nforged.md", secret) == ["notes\\nforged.md:1: GitHub token"]


def test_scan_never_reads_untracked_files_or_symlink_targets(tmp_path, monkeypatch) -> None:
    from scripts.repository_hygiene import scan_repository

    root = tmp_path / "repo"
    root.mkdir()
    secret = ("sk-proj-" + "a" * 40).encode()
    outside = tmp_path / "private.txt"
    outside.write_bytes(secret)
    (root / "reference").symlink_to(outside)
    (root / "untracked.env").write_bytes(secret)
    (root / "safe name\nwith newline.md").write_text("public example")
    # A replaced intermediate directory must not escape the repository either.
    (root / "linked").symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(
        "scripts.repository_hygiene.subprocess.check_output",
        lambda args: b"reference\0safe name\nwith newline.md\0linked/private.txt\0",
    )
    count, findings = scan_repository(root)
    assert count == 3
    assert findings == ["linked/private.txt: tracked path resolves outside repository"]
    assert secret.decode() not in "\n".join(findings)
