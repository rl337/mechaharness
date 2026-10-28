"""Injectable GitHub forge client (HTTP) for pull requests and CI logs.

``HttpGitHubClient`` takes :class:`~mechaharness.github_connection.GitHubConnectionConfig`
and :class:`~pyiv.http.AsyncHttpClient` via constructor injection — no ``gh``
CLI and no Settings bag. Hosts bind via ``ProjectCodingConfig.get_github_client()``.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from pyiv.http import AsyncHttpClient

from mechaharness.coding_git import CodingGitResult
from mechaharness.github_connection import GitHubConnectionConfig

_OWNER_REPO_SSH = re.compile(
    r"git@[^:]+:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?\s*$"
)
_OWNER_REPO_HTTPS = re.compile(
    r"https?://[^/]+/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?\s*$"
)
# Actions UI URLs: .../actions/runs/<run_id>/job/<job_id>
_JOB_ID_FROM_DETAILS = re.compile(r"/job/(?P<job_id>\d+)(?:\b|/|$)")


class GitHubClient(ABC):
    """Forge operations used by coding-delegate PR and CI tools."""

    @abstractmethod
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
        """Open a pull request; stdout should include the HTML URL when ok."""

    @abstractmethod
    def list_check_runs(
        self,
        *,
        owner: str,
        repo: str,
        ref: str,
    ) -> CodingGitResult:
        """List check runs for *ref*; stdout is a compact JSON summary."""

    @abstractmethod
    def get_workflow_job_logs(
        self,
        *,
        owner: str,
        repo: str,
        job_id: int | str,
        max_bytes: int = 120_000,
    ) -> CodingGitResult:
        """Download workflow job logs; stdout is truncated log text."""


class HttpGitHubClient(GitHubClient):
    """GitHub REST via injected HTTP + connection config."""

    def __init__(
        self,
        connection: GitHubConnectionConfig,
        client: AsyncHttpClient,
    ) -> None:
        self._connection = connection
        self._client = client

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
        if not self._connection.enabled():
            return CodingGitResult(
                ok=False, error="GitHubConnectionConfig has no token"
            )
        title_text = (title or "").strip()
        if not title_text:
            return CodingGitResult(ok=False, error="title required")
        owner_t = (owner or "").strip()
        repo_t = (repo or "").strip()
        head_t = (head or "").strip()
        if not owner_t or not repo_t or not head_t:
            return CodingGitResult(
                ok=False,
                error="owner, repo, and head are required for HTTP pull requests",
            )
        url = self._connection.endpoint(f"/repos/{owner_t}/{repo_t}/pulls")
        payload = {
            "title": title_text,
            "body": body if body is not None else "",
            "head": head_t,
            "base": (base or "main").strip() or "main",
            "draft": bool(draft),
        }
        try:
            response = _run_sync(
                self._client.request(
                    "POST",
                    url,
                    headers=self._connection.headers(),
                    json=payload,
                    timeout=self._connection.timeout_seconds,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return CodingGitResult(ok=False, error=str(exc))
        status = int(getattr(response, "status_code", 0) or 0)
        text = _response_text(response)
        if status not in {200, 201}:
            return CodingGitResult(
                ok=False,
                returncode=status,
                stdout=text[-8000:],
                error=f"GitHub API HTTP {status}",
            )
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            data = {}
        html_url = str(data.get("html_url") or "").strip()
        return CodingGitResult(
            ok=True,
            returncode=status,
            stdout=(html_url + "\n") if html_url else text[-8000:],
            extra={
                "html_url": html_url,
                "number": data.get("number"),
                "owner": owner_t,
                "repo": repo_t,
            },
        )

    def list_check_runs(
        self,
        *,
        owner: str,
        repo: str,
        ref: str,
    ) -> CodingGitResult:
        if not self._connection.enabled():
            return CodingGitResult(
                ok=False, error="GitHubConnectionConfig has no token"
            )
        owner_t = (owner or "").strip()
        repo_t = (repo or "").strip()
        ref_t = (ref or "").strip()
        if not owner_t or not repo_t or not ref_t:
            return CodingGitResult(
                ok=False, error="owner, repo, and ref are required"
            )
        url = self._connection.endpoint(
            f"/repos/{owner_t}/{repo_t}/commits/{ref_t}/check-runs"
        )
        try:
            response = _run_sync(
                self._client.request(
                    "GET",
                    url,
                    headers=self._connection.headers(),
                    timeout=self._connection.timeout_seconds,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return CodingGitResult(ok=False, error=str(exc))
        status = int(getattr(response, "status_code", 0) or 0)
        text = _response_text(response)
        if status != 200:
            return CodingGitResult(
                ok=False,
                returncode=status,
                stdout=text[-8000:],
                error=f"GitHub API HTTP {status}",
            )
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            return CodingGitResult(
                ok=False, returncode=status, error="invalid JSON from check-runs"
            )
        runs = data.get("check_runs") or []
        summary = []
        for r in runs:
            if not isinstance(r, dict):
                continue
            details = r.get("details_url")
            entry = {
                "id": r.get("id"),
                "name": r.get("name"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "html_url": r.get("html_url"),
                "details_url": details,
            }
            job_id = job_id_from_details_url(
                details if isinstance(details, str) else None
            )
            if job_id is not None:
                entry["job_id"] = job_id
            summary.append(entry)
        failed = [
            s
            for s in summary
            if str(s.get("conclusion") or "").lower()
            in {"failure", "timed_out", "cancelled", "action_required"}
        ]
        payload = {
            "total": len(summary),
            "failed": failed,
            "check_runs": summary,
            "owner": owner_t,
            "repo": repo_t,
            "ref": ref_t,
        }
        return CodingGitResult(
            ok=True,
            returncode=status,
            stdout=json.dumps(payload, indent=2) + "\n",
            extra=payload,
        )

    def get_workflow_job_logs(
        self,
        *,
        owner: str,
        repo: str,
        job_id: int | str,
        max_bytes: int = 120_000,
    ) -> CodingGitResult:
        if not self._connection.enabled():
            return CodingGitResult(
                ok=False, error="GitHubConnectionConfig has no token"
            )
        owner_t = (owner or "").strip()
        repo_t = (repo or "").strip()
        job = str(job_id or "").strip()
        if not owner_t or not repo_t or not job:
            return CodingGitResult(
                ok=False, error="owner, repo, and job_id are required"
            )
        url = self._connection.endpoint(
            f"/repos/{owner_t}/{repo_t}/actions/jobs/{job}/logs"
        )
        try:
            status, headers, body = _http_no_redirect(
                "GET",
                url,
                headers=self._connection.headers(),
                timeout=self._connection.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            return CodingGitResult(ok=False, error=str(exc))
        location = headers.get("Location") or headers.get("location")
        if status in {301, 302, 307, 308} and location:
            try:
                response = _run_sync(
                    self._client.request(
                        "GET",
                        str(location),
                        headers={"Accept": "application/octet-stream"},
                        timeout=self._connection.timeout_seconds,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                return CodingGitResult(ok=False, error=str(exc))
            status = int(getattr(response, "status_code", 0) or 0)
            text = _response_text(response)
        else:
            text = (
                body.decode("utf-8", errors="replace")
                if isinstance(body, bytes)
                else str(body)
            )
            if status != 200:
                return CodingGitResult(
                    ok=False,
                    returncode=status,
                    stdout=text[-8000:],
                    error=f"GitHub API HTTP {status}",
                )
        if status != 200:
            return CodingGitResult(
                ok=False,
                returncode=status,
                stdout=text[-8000:],
                error=f"GitHub API HTTP {status}",
            )
        limit = max(4_000, int(max_bytes))
        truncated = text[-limit:]
        return CodingGitResult(
            ok=True,
            returncode=status,
            stdout=truncated,
            extra={
                "owner": owner_t,
                "repo": repo_t,
                "job_id": job,
                "bytes": len(text),
                "truncated": len(text) > limit,
            },
        )


def job_id_from_details_url(details_url: str | None) -> str | None:
    """Extract Actions ``job_id`` from a check-run ``details_url`` when present."""
    text = (details_url or "").strip()
    if not text:
        return None
    match = _JOB_ID_FROM_DETAILS.search(text)
    return match.group("job_id") if match else None


def parse_github_owner_repo(remote_url: str) -> tuple[str, str] | None:
    """Parse ``owner/repo`` from an SSH or HTTPS GitHub remote URL."""
    text = (remote_url or "").strip()
    for rx in (_OWNER_REPO_SSH, _OWNER_REPO_HTTPS):
        match = rx.search(text)
        if match:
            return match.group("owner"), match.group("repo")
    return None


class RecordingGitHubClient(GitHubClient):
    """In-memory forge for stories/CI — records calls, returns canned CI data.

    Bind via story ``environment.coding_github: local_mock_ci`` so
    ``ci_checks`` / ``ci_job_log`` register without network or tokens.
    """

    DEFAULT_JOB_ID = "9001"

    DEFAULT_FAILING_LOG = (
        "Job: checks\n"
        "Step: Run checks\n"
        "Conclusion: failure\n"
        "\n"
        "Running: Ruff lint\n"
        "Command: ruff check src tests\n"
        "I001 [*] Import block is un-sorted or un-formatted\n"
        "  --> src/mechaharness/project_coding.py:10:1\n"
        "Found 4 errors.\n"
        "✗ Ruff lint failed (exit code: 1)\n"
        "\n"
        "Running: Mypy type checking\n"
        "Command: mypy\n"
        "src/mechaharness/github_client.py:550: error: Function is missing a "
        "type annotation  [no-untyped-def]\n"
        "src/mechaharness/generator_local_work.py:438: error: Incompatible "
        "types in assignment  [assignment]\n"
        "Found 2 errors in 2 files (checked 207 source files)\n"
        "✗ Mypy type checking failed (exit code: 1)\n"
        "\n"
        "E   ModuleNotFoundError: No module named 'widget'\n"
        "✗ Pytest failed (exit code: 2)\n"
        "FAIL Required test coverage of 78.0% not reached. Total coverage: 77.55%\n"
        "Some checks failed. Please fix the issues above.\n"
    )

    def __init__(
        self,
        *,
        check_runs: list[dict[str, Any]] | None = None,
        job_logs: dict[str, str] | None = None,
        pr_url: str = "https://example.test/pull/1",
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._pr_url = str(pr_url)
        job_id = self.DEFAULT_JOB_ID
        if check_runs is None:
            check_runs = [
                {
                    "id": 1,
                    "name": "checks",
                    "status": "completed",
                    "conclusion": "failure",
                    "html_url": "https://example.test/checks/1",
                    "details_url": (
                        "https://github.com/acme/demo/actions/runs/1/"
                        f"job/{job_id}"
                    ),
                }
            ]
        self._check_runs = list(check_runs)
        if job_logs is None:
            job_logs = {job_id: self.DEFAULT_FAILING_LOG}
        self._job_logs = {str(k): str(v) for k, v in job_logs.items()}

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
        title_text = (title or "").strip()
        if not title_text:
            return CodingGitResult(ok=False, error="title required")
        record = {
            "op": "create_pull_request",
            "owner": owner,
            "repo": repo,
            "title": title_text,
            "body": body if body is not None else "",
            "head": head,
            "base": base,
            "draft": bool(draft),
            "url": self._pr_url,
        }
        self.calls.append(record)
        return CodingGitResult(
            ok=True,
            stdout=self._pr_url + "\n",
            extra={"html_url": self._pr_url, "number": 1},
        )

    def list_check_runs(
        self,
        *,
        owner: str,
        repo: str,
        ref: str,
    ) -> CodingGitResult:
        self.calls.append(
            {
                "op": "list_check_runs",
                "owner": owner,
                "repo": repo,
                "ref": ref,
            }
        )
        summary: list[dict[str, Any]] = []
        for r in self._check_runs:
            entry = dict(r)
            details = entry.get("details_url")
            if "job_id" not in entry:
                job_id = job_id_from_details_url(
                    details if isinstance(details, str) else None
                )
                if job_id is not None:
                    entry["job_id"] = job_id
            summary.append(entry)
        failed = [
            s
            for s in summary
            if str(s.get("conclusion") or "").lower()
            in {"failure", "timed_out", "cancelled", "action_required"}
        ]
        payload = {
            "total": len(summary),
            "failed": failed,
            "check_runs": summary,
            "owner": owner,
            "repo": repo,
            "ref": ref,
        }
        return CodingGitResult(
            ok=True,
            stdout=json.dumps(payload, indent=2) + "\n",
            extra=payload,
        )

    def get_workflow_job_logs(
        self,
        *,
        owner: str,
        repo: str,
        job_id: int | str,
        max_bytes: int = 120_000,
    ) -> CodingGitResult:
        job = str(job_id or "").strip()
        self.calls.append(
            {
                "op": "get_workflow_job_logs",
                "owner": owner,
                "repo": repo,
                "job_id": job,
                "max_bytes": int(max_bytes),
            }
        )
        text = self._job_logs.get(job)
        if text is None:
            return CodingGitResult(
                ok=False,
                error=f"no canned log for job_id={job!r}",
            )
        limit = max(4_000, int(max_bytes))
        truncated = text[-limit:]
        return CodingGitResult(
            ok=True,
            stdout=truncated,
            extra={
                "owner": owner,
                "repo": repo,
                "job_id": job,
                "bytes": len(text),
                "truncated": len(text) > limit,
            },
        )


def _response_text(response: Any) -> str:
    body = getattr(response, "text", None)
    if callable(body):
        try:
            body = body()
        except TypeError:
            pass
    if body is None:
        raw = getattr(response, "content", b"") or b""
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)
    return str(body)


def _run_sync(awaitable: Any) -> Any:
    """Run an async HTTP call from sync CodingGit tool handlers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(awaitable)).result()


def _http_no_redirect(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, dict[str, str], bytes]:
    """HTTP request that does not follow redirects (capture ``Location``)."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(
            self,
            req: urllib.request.Request,
            fp: Any,
            code: int,
            msg: str,
            headers: Any,
            newurl: str,
        ) -> urllib.request.Request | None:
            del req, fp, code, msg, headers, newurl
            return None

    request = urllib.request.Request(url, method=method.upper(), headers=dict(headers))
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=float(timeout)) as response:
            return (
                int(response.getcode()),
                {k: v for k, v in response.headers.items()},
                response.read(),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        hdrs = dict(exc.headers.items()) if exc.headers else {}
        return int(exc.code), hdrs, body or b""


__all__ = [
    "GitHubClient",
    "HttpGitHubClient",
    "RecordingGitHubClient",
    "job_id_from_details_url",
    "parse_github_owner_repo",
]
