"""Check tracked files for local artifacts and recognizable credentials.

Findings contain paths, line numbers and categories, never matched values.
This checks the working content of tracked paths, not all historical revisions.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath

_LOCAL_PARTS = frozenset({
    "__pycache__", ".env", ".venv", ".codex", ".aws", ".mechaharness",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
})
_LOCAL_PREFIXES = ("docs/plans/", "docs/adr/", "docs/_build/", "build/", "dist/")
_LOCAL_NAMES = frozenset({
    ".DS_Store", ".envrc", ".pypirc", ".coverage", "coverage-stories.json",
})
_CONTENT_PATTERNS = {
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "OpenAI project key": r"sk-proj-[A-Za-z0-9_-]{20,}",
    "GitHub token": r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{35,})",
    "AWS access key": r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "absolute home path": r"/(?:Users|home)/[A-Za-z0-9_.-]+/",
    "private endpoint": (
        r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
}


def path_issue(name: str) -> str | None:
    """Return a reason for a local artifact path; examples and fixtures stay valid."""
    path = PurePosixPath(name)
    if any(part in _LOCAL_PARTS for part in path.parts) or name.startswith(_LOCAL_PREFIXES):
        return "local directory"
    if path.name in _LOCAL_NAMES or name == ".cursor/mcp.json":
        return "local configuration or report"
    if path.name.startswith(".env.") and path.name != ".env.example":
        return "dotenv secrets file"
    if path.suffix in {".pyc", ".pyo"} or any(p.endswith(".egg-info") for p in path.parts):
        return "generated Python artifact"
    return None


def content_issues(name: str, content: bytes) -> list[str]:
    """Return redacted findings for recognizable text patterns; skip binary files."""
    if b"\0" in content:
        return []
    findings = []
    for number, line in enumerate(content.decode("utf-8", errors="replace").splitlines(), 1):
        for category, pattern in _CONTENT_PATTERNS.items():
            if re.search(pattern, line):
                findings.append(f"{_display_name(name)}:{number}: {category}")
    return findings


def _display_name(name: str) -> str:
    """Escape control characters so filenames cannot forge additional log entries."""
    return name.encode("unicode_escape").decode("ascii")


def scan_repository(root: Path) -> tuple[int, list[str]]:
    """Scan tracked paths only, so local secrets are neither read nor reported."""
    names = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z"],
    ).decode().split("\0")
    findings = []
    count = 0
    for name in filter(None, names):
        count += 1
        reason = path_issue(name)
        if reason:
            findings.append(f"{_display_name(name)}: {reason}")
            continue
        path = root / name
        if path.is_symlink():
            # Inspect the tracked link, never its potentially untracked target.
            content = os.readlink(path).encode()
        elif root.resolve() not in path.resolve().parents:
            findings.append(f"{_display_name(name)}: tracked path resolves outside repository")
            continue
        elif path.is_file():
            content = path.read_bytes()
        else:
            continue
        findings.extend(content_issues(name, content))
    return count, findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    count, findings = scan_repository(root)
    for finding in findings:
        print(finding)
    print(f"Repository hygiene: {count} tracked paths, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
