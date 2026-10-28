"""Unit tests for HttpGitHubClient, RecordingGitHubClient, and URL parsing."""

from __future__ import annotations

import pytest
from pyiv.http import MemoryAsyncHttpClient

from mechaharness.github_client import (
    HttpGitHubClient,
    RecordingGitHubClient,
    job_id_from_details_url,
    parse_github_owner_repo,
)
from mechaharness.github_connection import GitHubConnectionConfig


def test_parse_github_owner_repo_ssh_and_https() -> None:
    assert parse_github_owner_repo("git@github.com:acme/demo.git") == ("acme", "demo")
    assert parse_github_owner_repo("https://github.com/acme/demo.git") == ("acme", "demo")
    assert parse_github_owner_repo("not-a-remote") is None


def test_job_id_from_details_url() -> None:
    cases = (
        (
            "https://github.com/acme/demo/actions/runs/1/job/9001",
            "9001",
        ),
        ("https://example.test/checks/1", None),
        (None, None),
        ("", None),
    )
    for url, expected in cases:
        assert job_id_from_details_url(url) == expected


def test_recording_github_client_ci_lookup() -> None:
    github = RecordingGitHubClient()
    checks = github.list_check_runs(owner="acme", repo="demo", ref="abc")
    assert checks.ok
    assert checks.extra["failed"][0]["job_id"] == RecordingGitHubClient.DEFAULT_JOB_ID
    logs = github.get_workflow_job_logs(
        owner="acme",
        repo="demo",
        job_id=RecordingGitHubClient.DEFAULT_JOB_ID,
    )
    assert logs.ok
    assert "Ruff" in logs.stdout
    assert [c["op"] for c in github.calls] == [
        "list_check_runs",
        "get_workflow_job_logs",
    ]


def test_http_github_client_create_pull_request() -> None:
    client = MemoryAsyncHttpClient()
    client.add(
        "POST",
        "https://api.github.com/repos/acme/demo/pulls",
        json={
            "html_url": "https://github.com/acme/demo/pull/42",
            "number": 42,
        },
        status_code=201,
    )
    github = HttpGitHubClient(
        connection=GitHubConnectionConfig(token="test-token"),
        client=client,
    )
    result = github.create_pull_request(
        owner="acme",
        repo="demo",
        title="Ship it",
        body="## Summary\n- done\n",
        head="feature",
        base="main",
    )
    assert result.ok
    assert "pull/42" in result.stdout


def test_http_github_client_list_check_runs() -> None:
    client = MemoryAsyncHttpClient()
    client.add(
        "GET",
        "https://api.github.com/repos/acme/demo/commits/abc123/check-runs",
        json={
            "total_count": 1,
            "check_runs": [
                {
                    "id": 1,
                    "name": "checks",
                    "status": "completed",
                    "conclusion": "failure",
                    "html_url": "https://example.test/checks/1",
                    "details_url": (
                        "https://github.com/acme/demo/actions/runs/9/job/9001"
                    ),
                }
            ],
        },
        status_code=200,
    )
    github = HttpGitHubClient(
        connection=GitHubConnectionConfig(token="test-token"),
        client=client,
    )
    result = github.list_check_runs(owner="acme", repo="demo", ref="abc123")
    assert result.ok
    assert result.extra["failed"][0]["name"] == "checks"
    assert result.extra["failed"][0]["job_id"] == "9001"


def test_http_github_client_get_workflow_job_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mechaharness.github_client as github_client_mod

    def _fake_no_redirect(method, url, *, headers, timeout):  # noqa: ANN001
        del method, headers, timeout
        assert url.endswith("/actions/jobs/99/logs")
        return (302, {"Location": "https://signed.example.test/logs.bin"}, b"")

    monkeypatch.setattr(github_client_mod, "_http_no_redirect", _fake_no_redirect)
    client = MemoryAsyncHttpClient()
    client.add(
        "GET",
        "https://signed.example.test/logs.bin",
        body=b"Step: Run checks\nE   TypeError: boom\n",
        status_code=200,
    )
    github = HttpGitHubClient(
        connection=GitHubConnectionConfig(token="test-token"),
        client=client,
    )
    result = github.get_workflow_job_logs(
        owner="acme", repo="demo", job_id=99, max_bytes=10_000
    )
    assert result.ok
    assert "TypeError" in result.stdout


def test_http_github_client_requires_token() -> None:
    github = HttpGitHubClient(
        connection=GitHubConnectionConfig(token=None),
        client=MemoryAsyncHttpClient(),
    )
    result = github.list_check_runs(owner="acme", repo="demo", ref="main")
    assert not result.ok
