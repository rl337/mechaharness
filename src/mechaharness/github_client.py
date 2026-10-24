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
        summary = [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "html_url": r.get("html_url"),
                "details_url": r.get("details_url"),
            }
            for r in runs
            if isinstance(r, dict)
        ]
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


def parse_github_owner_repo(remote_url: str) -> tuple[str, str] | None:
    """Parse ``owner/repo`` from an SSH or HTTPS GitHub remote URL."""
    text = (remote_url or "").strip()
    for rx in (_OWNER_REPO_SSH, _OWNER_REPO_HTTPS):
        match = rx.search(text)
        if match:
            return match.group("owner"), match.group("repo")
    return None


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
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):  # noqa: ANN001
            del req, fp, code, msg, hdrs, newurl
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
    "parse_github_owner_repo",
]
