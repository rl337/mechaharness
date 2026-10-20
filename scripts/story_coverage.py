#!/usr/bin/env python3
"""Run user-story coverage, print gaps, and enforce the configured floor.

Uses ``[tool.coverage.*]`` from ``pyproject.toml``. Exit non-zero when the
story suite falls below ``fail_under`` (coverage not allowed to drop).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "coverage-stories.json"


def _run_pytest_cov() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/stories/test_user_stories.py",
        "-q",
        "--cov=mechaharness",
        "--cov-config=pyproject.toml",
        "--cov-report=term:skip-covered",
        "--cov-report=json",
    ]
    print("Command:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=ROOT)


def _print_gaps(data: dict) -> None:
    files = data.get("files") or {}
    rows: list[tuple[float, int, int, str]] = []
    for path, info in files.items():
        summary = info["summary"]
        pct = float(summary["percent_covered"])
        stmts = int(summary["num_statements"])
        covered = int(summary["covered_lines"])
        rel = path.replace("src/mechaharness/", "").replace("\\", "/")
        if "mechaharness/" in rel:
            rel = rel.split("mechaharness/", 1)[-1]
        rows.append((pct, stmts - covered, stmts, rel))
    rows.sort(key=lambda row: (row[0], -row[2], row[3]))

    totals = data["totals"]
    print()
    print(
        f"Story coverage: {totals['percent_covered']:.2f}% "
        f"(statements={totals['num_statements']}, "
        f"covered={totals['covered_lines']}, "
        f"branches={totals.get('num_branches', 0)})"
    )

    zeros = [row for row in rows if row[0] == 0.0 and row[2] > 0]
    low = [row for row in rows if 0.0 < row[0] < 50.0]
    mid = [row for row in rows if 50.0 <= row[0] < 80.0]

    print()
    print(
        "Positive-path rule: product modules should be hit via Config + mock/"
        "cassette story init (host.family / host.backend), not probe-local DI. "
        "Refusal stories still count as coverage."
    )

    print()
    print("=== Gaps: 0% under user stories (product positive-path debt) ===")
    if not zeros:
        print("  (none)")
    for _pct, _miss, stmts, path in zeros:
        print(f"  {path:52} stmts={stmts}")

    print()
    print("=== Gaps: <50% under user stories ===")
    if not low:
        print("  (none)")
    for pct, miss, stmts, path in low:
        print(f"  {pct:5.1f}%  {path:52} miss={miss}/{stmts}")

    print()
    print("=== Partial: 50–80% under user stories ===")
    if not mid:
        print("  (none)")
    for pct, miss, stmts, path in mid[:25]:
        print(f"  {pct:5.1f}%  {path:52} miss={miss}/{stmts}")
    if len(mid) > 25:
        print(f"  … +{len(mid) - 25} more")


def main() -> int:
    code = _run_pytest_cov()
    if not JSON_PATH.is_file():
        print("coverage JSON missing; pytest-cov did not write a report", file=sys.stderr)
        return code or 1
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    _print_gaps(data)
    # pytest-cov already enforces fail_under via coverage report; surface clearly.
    if code != 0:
        print()
        print(
            "Story coverage gate failed (see fail_under in pyproject.toml "
            "[tool.coverage.report]). Bump the floor when coverage improves; "
            "do not lower it to silence a drop.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
