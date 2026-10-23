#!/usr/bin/env python3
"""Author fangore_counter_* stories + sequential counter_pkg suite.json.

Multi-file package arc (library + tests + CLI) — the next coding-delegate
suite after ``calc_cli``. See ``docs/plans/coding-delegate-suites.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "tests/fixtures/models/static/fixture/v1/stories"
SUITE_DIR = ROOT / "tests/fixtures/models/static/fixture/v1/suites/counter_pkg"
SOURCES = SUITE_DIR / "sources"

PKG_SHAPE = (
    "Required contracts (non-negotiable): keep package import `from counter import "
    "Counter` working; public class must be named `Counter`. Do NOT use eval() or "
    "exec(). You MUST call write_file for every file you create or change before "
    "finishing. Tests under tests/ must stay green (pytest)."
)

STAGES: list[dict[str, object]] = [
    {
        "story": "fangore_counter_bootstrap",
        "scenario": "bootstrap",
        "source_dir": "00_bootstrap",
        "title": "Bootstrap a Counter package with a failing-then-green test",
        "goal": (
            "Create a Python package `counter/` with `__init__.py` exporting "
            "`Counter` (start value 0, attribute `value`). Add `tests/test_counter.py` "
            "with a test that constructs Counter and asserts value == 0. "
            f"{PKG_SHAPE}"
        ),
        "narrative": (
            "Fangore hands an expensive bootstrap to guided coding: a tiny library "
            "package plus a pytest that pins the public constructor contract. Live "
            "mode uses a real Completer; static mode uses multi-file coding_writes "
            "stubs. This stage is the multi-file successor to `fangore_calc_parse_number`."
        ),
        "written": ["counter/__init__.py", "tests/test_counter.py"],
        "text_checks": [
            ("counter/__init__.py", ["class Counter", "value"]),
            ("tests/test_counter.py", ["Counter", "def test_"]),
        ],
        "pytest": ["tests/test_counter.py"],
        "run_python": [],
    },
    {
        "story": "fangore_counter_mutate",
        "scenario": "mutate",
        "source_dir": "01_mutate",
        "title": "Add increment and decrement while tests stay green",
        "goal": (
            "Extend `Counter` with `inc(n=1)` and `dec(n=1)` methods that mutate "
            "`value` and return the new value. Extend tests for inc/dec. Keep "
            f"constructor behavior. {PKG_SHAPE}"
        ),
        "narrative": (
            "Fangore continues the shared package workspace and asks guided coding "
            "to grow mutation methods without breaking the bootstrap test contract."
        ),
        "written": ["counter/__init__.py", "tests/test_counter.py"],
        "text_checks": [
            ("counter/__init__.py", ["def inc", "def dec"]),
            ("tests/test_counter.py", ["inc", "dec"]),
        ],
        "pytest": ["tests/test_counter.py"],
        "run_python": [],
    },
    {
        "story": "fangore_counter_persist",
        "scenario": "persist",
        "source_dir": "02_persist",
        "title": "Persist Counter state to a JSON file",
        "goal": (
            "Add `Counter.save(path)` and `Counter.load(path)` classmethod (or "
            "equivalent named `load`) that round-trip `value` as JSON. Extend "
            f"tests. Keep inc/dec. {PKG_SHAPE}"
        ),
        "narrative": (
            "Fangore asks for durable state on disk so later CLI work can reload "
            "counts — still under the same package and pytest gate."
        ),
        "written": ["counter/__init__.py", "tests/test_counter.py"],
        "text_checks": [
            ("counter/__init__.py", ["def save", "def load"]),
            ("tests/test_counter.py", ["save", "load"]),
        ],
        "pytest": ["tests/test_counter.py"],
        "run_python": [],
    },
    {
        "story": "fangore_counter_cli",
        "scenario": "cli",
        "source_dir": "03_cli",
        "title": "Add a CLI that drives Counter",
        "goal": (
            "Add `counter_cli.py` with `def main(argv=None) -> int` that supports "
            "`inc`, `dec`, and `show` subcommands using a `counter.json` file in "
            "the workspace (create on first use). Print the current value on "
            f"stdout. Keep the library and tests green. {PKG_SHAPE}"
        ),
        "narrative": (
            "Fangore finishes the delegate arc with a thin CLI over the library — "
            "the expensive work stays in the package; the CLI is the operator face."
        ),
        "written": ["counter_cli.py", "counter/__init__.py", "tests/test_counter.py"],
        "text_checks": [
            ("counter_cli.py", ["def main", "inc", "dec", "show"]),
            ("counter/__init__.py", ["class Counter"]),
        ],
        "pytest": ["tests/test_counter.py"],
        # verify_runs exercise a full inc/inc/show/dec cycle (ends at 1 and
        # leaves counter.json). Story run_python continues from that state.
        "run_python": [
            (["show"], "1"),
            (["inc"], "2"),
            (["dec"], "1"),
        ],
        "run_python_path": "counter_cli.py",
        "verify_cli": [
            (["inc"], "1"),
            (["inc"], "2"),
            (["show"], "2"),
            (["dec"], "1"),
        ],
    },
]


def _indent_block(text: str, spaces: int = 6) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line else pad.rstrip() for line in text.splitlines())


def _load_sources(source_dir: str) -> list[tuple[str, str]]:
    root = SOURCES / source_dir
    files: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            files.append((rel, path.read_text(encoding="utf-8")))
    if not files:
        raise FileNotFoundError(f"no sources under {root}")
    return files


def _scenario_yaml(stage: dict[str, object]) -> str:
    files = _load_sources(str(stage["source_dir"]))
    goal = json.dumps(str(stage["goal"]))
    written = list(stage["written"])  # type: ignore[arg-type]
    text_checks = list(stage["text_checks"])  # type: ignore[arg-type]
    pytest_paths = list(stage["pytest"])  # type: ignore[arg-type]
    run_python = list(stage.get("run_python") or [])
    verify_cli = list(stage.get("verify_cli") or run_python)
    run_path = str(stage.get("run_python_path") or "")

    writes_yaml_parts: list[str] = []
    for rel, content in files:
        writes_yaml_parts.append(
            "  - path: "
            + json.dumps(rel)
            + "\n    content: |\n"
            + _indent_block(content.rstrip("\n") + "\n", 6)
        )
    coding_writes = "\n".join(writes_yaml_parts)

    verify_runs: list[dict] = []
    for path, needles in text_checks:
        verify_runs.append(
            {
                "path": path,
                "text_contains": list(needles),
                "text_forbids": ["eval(", "exec("],
            }
        )
    for p in pytest_paths:
        verify_runs.append({"path": p, "pytest": True, "exit_code": 0})
    for args, expect in verify_cli:
        verify_runs.append(
            {
                "path": run_path,
                "args": list(args),
                "stdout_contains": expect,
                "exit_code": 0,
            }
        )
    verify_yaml = yaml.safe_dump(verify_runs, default_flow_style=False).rstrip()
    verify_indented = "\n".join(f"        {line}" for line in verify_yaml.splitlines())

    read_steps: list[str] = []
    for path, needles in text_checks:
        expect_items = [
            {"kind": "true", "key": "exists"},
            *[{"kind": "contains", "key": "text", "value": n} for n in needles],
        ]
        step = {
            "do": {"workspace_read": {"path": path}},
            "expect": expect_items,
        }
        dumped = yaml.safe_dump([step], default_flow_style=False).rstrip()
        read_steps.append(dumped)

    run_steps: list[str] = []
    for args, expect in run_python:
        step = {
            "do": {
                "run_python": {
                    "path": run_path,
                    "args": list(args),
                }
            },
            "expect": [
                {"kind": "equals", "key": "exit_code", "value": 0},
                {"kind": "contains", "key": "stdout", "value": expect},
            ],
        }
        dumped = yaml.safe_dump([step], default_flow_style=False).rstrip()
        run_steps.append(dumped)

    includes = yaml.safe_dump(written, default_flow_style=False).rstrip()
    includes_indented = "\n".join(f"    {line}" for line in includes.splitlines())

    body = f"""\
# user story: {stage["story"]}
# Sequential counter_pkg stage — multi-file package + pytest contracts.
# Static: coding_writes stubs. Live: Completer ignores stubs.
kind: user_story
environment:
  family: pass_through
  backend: mock
  local_work: project_coding
  workspace: suite
  coding_writes:
{coding_writes}
graph:
  recipe: guided_coding
  durable:
    controller: story
    store: memory
steps:
- do:
    start:
      run_id: counter-{stage["scenario"]}
      inputs:
        goal: {goal}
        max_iterations: 24
        verify_runs:
{verify_indented}
  expect:
  - kind: equals
    key: kind
    value: advice_requested
  - kind: gte
    key: guidance_yields
    value: 1
  - kind: gte
    key: local_steps
    value: 1
- do:
    answer:
      choose: minimal
  expect:
  - kind: equals
    key: kind
    value: completed
  - kind: gte
    key: resumes
    value: 1
  - kind: includes
    key: written_files
    value:
{includes_indented}
{chr(10).join(read_steps + run_steps)}
complete:
  expect:
  - kind: includes
    key: event_types
    value:
    - core:graph_yield
    - core:guidance_resume
    - core:graph_start
    - core:graph_end
cleanup: []
"""
    yaml.safe_load(body)
    return body


def _story_json(stage: dict[str, object]) -> dict:
    story_id = str(stage["story"])
    scenario = str(stage["scenario"])
    return {
        "id": story_id,
        "persona": "fangore",
        "title": stage["title"],
        "kind": "user_story",
        "narrative": stage["narrative"],
        "implementation": (
            "Agentic Recipe catalog id `guided_coding` with "
            "`environment.local_work: project_coding`, "
            "`environment.workspace: suite`, and multi-file "
            "`coding_writes` offline stubs. Live mode binds "
            "`completer_as_tool_loop_complete`. Host `verify_runs` include "
            "`pytest: true` and `text_contains` / `text_forbids` with repair."
        ),
        "validation": (
            f"Harness `user_story` scenario `{scenario}.yaml` inside sequential "
            "suite `counter_pkg` (ordered). Live eligibility: "
            "`environment.local_work: project_coding`."
        ),
        "footnotes": [],
    }


def write_all() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    stages_payload: list[dict[str, str]] = []
    for stage in STAGES:
        story_id = str(stage["story"])
        scenario = str(stage["scenario"])
        story_dir = STORIES / story_id
        scenarios_dir = story_dir / "scenarios"
        scenarios_dir.mkdir(parents=True, exist_ok=True)
        (story_dir / "story.json").write_text(
            json.dumps(_story_json(stage), indent=2) + "\n",
            encoding="utf-8",
        )
        (scenarios_dir / f"{scenario}.yaml").write_text(
            _scenario_yaml(stage),
            encoding="utf-8",
        )
        stages_payload.append({"story": story_id, "scenario": scenario})

    suite = {
        "id": "counter_pkg",
        "title": "Grow a Counter package with tests and CLI",
        "persona": "fangore",
        "execution": {"mode": "sequential", "ordered": True},
        "vars": {},
        "setup": ["ensure_workspace"],
        "cleanup": [],
        "workspace": "temp",
        "stages": stages_payload,
    }
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    (SUITE_DIR / "suite.json").write_text(
        json.dumps(suite, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(STAGES)} counter stories + {SUITE_DIR / 'suite.json'}")


if __name__ == "__main__":
    write_all()
