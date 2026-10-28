"""GitHub HTTP reachability config (token + API base).

Owns ``MECHA_GITHUB_*`` / ``GITHUB_TOKEN`` — not ``Settings``. Bind via
``ProjectCodingConfig.get_github_connection()`` and inject into
:class:`~mechaharness.github_client.GitHubClient`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyiv.process import Environment, OsEnvironment


@dataclass(frozen=True)
class GitHubConnectionConfig:
    """How to reach the GitHub (or GHES) HTTP API for pull requests and CI."""

    api_base: str = "https://api.github.com"
    token: str | None = None
    timeout_seconds: float = 60.0
    owner: str | None = None
    repo: str | None = None
    api_version: str = "2022-11-28"

    def enabled(self) -> bool:
        return bool((self.token or "").strip())

    def endpoint(self, path: str) -> str:
        base = (self.api_base or "https://api.github.com").rstrip("/")
        suffix = path if path.startswith("/") else f"/{path}"
        return f"{base}{suffix}"

    def headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.api_version,
        }
        token = (self.token or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @classmethod
    def from_env(
        cls, env: Environment | None = None
    ) -> GitHubConnectionConfig:
        """Read ``MECHA_GITHUB_*`` with ``GITHUB_TOKEN`` fallback.

        Keys: ``MECHA_GITHUB_TOKEN`` (or ``GITHUB_TOKEN``),
        ``MECHA_GITHUB_API_BASE``, ``MECHA_GITHUB_OWNER``,
        ``MECHA_GITHUB_REPO``, ``MECHA_GITHUB_TIMEOUT_SECONDS``.
        """
        environ = env if env is not None else OsEnvironment()

        def _get(*keys: str) -> str | None:
            for key in keys:
                value = environ.get(key)
                if value is not None and str(value).strip() != "":
                    return str(value).strip()
            return None

        timeout_raw = _get("MECHA_GITHUB_TIMEOUT_SECONDS")
        timeout = 60.0
        if timeout_raw is not None:
            try:
                timeout = float(timeout_raw)
            except ValueError:
                timeout = 60.0
        return cls(
            api_base=_get("MECHA_GITHUB_API_BASE") or "https://api.github.com",
            token=_get("MECHA_GITHUB_TOKEN", "GITHUB_TOKEN"),
            timeout_seconds=timeout,
            owner=_get("MECHA_GITHUB_OWNER"),
            repo=_get("MECHA_GITHUB_REPO"),
        )


__all__ = ["GitHubConnectionConfig"]
