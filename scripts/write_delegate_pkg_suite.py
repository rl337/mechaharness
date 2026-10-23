#!/usr/bin/env python3
"""Author fangore_delegate_* stories + sequential delegate_pkg suite.json.

One suite covers the remaining coding-delegate arcs after calc_cli / counter_pkg:
list-mode coding, substantive guidance fork, red-green fix, and rename refactor.
Live Completer is the gate; static coding_writes are provisional until live passes.
See ``docs/plans/coding-delegate-suites.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "tests/fixtures/models/static/fixture/v1/stories"
SUITE_DIR = ROOT / "tests/fixtures/models/static/fixture/v1/suites/delegate_pkg"
SOURCES = SUITE_DIR / "sources"

PKG_SHAPE = (
    "Required contracts (non-negotiable): keep package import "
    "`from widget import …` working. Do NOT use eval() or exec(). You MUST call "
    "write_file for every file you create or change before finishing. Tests under "
    "tests/ must stay green (pytest)."
)

STAGES: list[dict[str, object]] = [
    {
        "story": "fangore_delegate_list_bootstrap",
        "scenario": "list_bootstrap",
        "source_dir": "00_list_bootstrap",
        "title": "Bootstrap a Widget package from a numbered todo list",
        "choose": "minimal",
        "inputs": {
            "instruction_mode": "list",
            "instructions": [
                (
                    "Create package `widget/` with `__init__.py` exporting class "
                    "`Widget` (start value 0, attribute `value`)."
                ),
                (
                    "Add `tests/test_widget.py` with a test that constructs Widget "
                    "and asserts value == 0."
                ),
            ],
            "goal": (
                "Follow the instruction list in order. "
                f"{PKG_SHAPE} Public class must be named `Widget`."
            ),
            "max_iterations": 24,
        },
        "narrative": (
            "Fangore hands a multi-step bootstrap as an ordered instruction list "
            "so guided coding classifies list mode and runs a coding burst per "
            "todo under shared workspace acceptance. Live Completer is the proof "
            "gate; static multi-file stubs are only a provisional mirror. "
            "Complements `fangore_instruction_todo_plan` (plan-only) and "
            "`fangore_counter_bootstrap` (oneshot package bootstrap)."
        ),
        "written": ["widget/__init__.py", "tests/test_widget.py"],
        "text_checks": [
            ("widget/__init__.py", ["class Widget", "value"]),
            ("tests/test_widget.py", ["Widget", "def test_"]),
        ],
        "pytest": ["tests/test_widget.py"],
        "extra_answer_expects": [
            {"kind": "equals", "key": "mode", "value": "list"},
        ],
    },
    {
        "story": "fangore_delegate_guidance_thorough",
        "scenario": "guidance_thorough",
        "source_dir": "01_guidance_thorough",
        "title": "Honor thorough guidance by shipping code and README together",
        "choose": "thorough",
        "inputs": {
            "goal": (
                "Extend `Widget` with `inc(n=1)` that mutates `value` and returns "
                "the new value. Extend tests for inc. Honor external guidance: "
                "when the driver chooses thorough, also write `README.md` with a "
                "`## Usage` section showing `from widget import Widget`. When "
                "minimal, skip the README. "
                f"{PKG_SHAPE}"
            ),
            "max_iterations": 24,
        },
        "narrative": (
            "Fangore continues the shared Widget workspace and answers the "
            "external guidance soft point with thorough so the delegate must "
            "ship the code change and a README in the same burst — proving "
            "mid-arc human direction changes artifacts, not only labels."
        ),
        "written": [
            "widget/__init__.py",
            "tests/test_widget.py",
            "README.md",
        ],
        "text_checks": [
            ("widget/__init__.py", ["def inc"]),
            ("tests/test_widget.py", ["inc"]),
            ("README.md", ["## Usage", "from widget import Widget"]),
        ],
        "pytest": ["tests/test_widget.py"],
        "extra_answer_expects": [],
    },
    {
        "story": "fangore_delegate_red_green",
        "scenario": "red_green",
        "source_dir": "02_red_green",
        "title": "Add a failing test then implement until pytest is green",
        "choose": "minimal",
        "inputs": {
            "goal": (
                "Add `Widget.double()` that doubles `value` and returns the new "
                "value. Ensure `tests/test_widget.py` includes `test_double` that "
                "would fail before the method exists, then implement so pytest is "
                "green. Keep inc and README. "
                f"{PKG_SHAPE}"
            ),
            "max_iterations": 24,
        },
        "narrative": (
            "Fangore asks the delegate to fix from a red test: pin "
            "`double()` in pytest first, then implement until the suite is green "
            "under verify_repair — the classic expensive coding handoff."
        ),
        "written": ["widget/__init__.py", "tests/test_widget.py"],
        "text_checks": [
            ("widget/__init__.py", ["def double"]),
            ("tests/test_widget.py", ["test_double", "double"]),
        ],
        "pytest": ["tests/test_widget.py"],
        "extra_answer_expects": [],
    },
    {
        "story": "fangore_delegate_refactor",
        "scenario": "refactor",
        "source_dir": "03_refactor",
        "title": "Rename Widget to Gadget without breaking tests",
        "choose": "minimal",
        "inputs": {
            "goal": (
                "Rename the public class `Widget` to `Gadget` everywhere "
                "(package, tests, README). Keep the package import path "
                "`from widget import Gadget`. Keep inc and double behavior. "
                f"{PKG_SHAPE}"
            ),
            "max_iterations": 24,
        },
        "narrative": (
            "Fangore finishes the delegate arc with a rename refactor: the "
            "public type moves from Widget to Gadget while pytest and docs stay "
            "honest — proving the handoff can reshape APIs without contract drift."
        ),
        "written": [
            "widget/__init__.py",
            "tests/test_widget.py",
            "README.md",
        ],
        "text_checks": [
            ("widget/__init__.py", ["class Gadget", "def double"]),
            ("tests/test_widget.py", ["Gadget", "test_double"]),
            ("README.md", ["Gadget", "from widget import Gadget"]),
        ],
        "pytest": ["tests/test_widget.py"],
        "text_forbids_extra": {
            "widget/__init__.py": ["class Widget"],
            "tests/test_widget.py": ["Widget"],
        },
        "extra_answer_expects": [],
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
    written = list(stage["written"])  # type: ignore[arg-type]
    text_checks = list(stage["text_checks"])  # type: ignore[arg-type]
    pytest_paths = list(stage["pytest"])  # type: ignore[arg-type]
    inputs = dict(stage["inputs"])  # type: ignore[arg-type]
    choose = str(stage["choose"])
    extra_answer = list(stage.get("extra_answer_expects") or [])
    forbids_extra = dict(stage.get("text_forbids_extra") or {})  # type: ignore[arg-type]

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
        forbids = ["eval(", "exec("]
        forbids.extend(forbids_extra.get(path, []))
        verify_runs.append(
            {
                "path": path,
                "text_contains": list(needles),
                "text_forbids": forbids,
            }
        )
    for p in pytest_paths:
        verify_runs.append({"path": p, "pytest": True, "exit_code": 0})

    # Fold verify_runs into start inputs for YAML dump of the whole inputs bag.
    start_inputs = {**inputs, "verify_runs": verify_runs}
    inputs_yaml = yaml.safe_dump(start_inputs, default_flow_style=False).rstrip()
    inputs_indented = "\n".join(f"        {line}" for line in inputs_yaml.splitlines())

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

    includes = yaml.safe_dump(written, default_flow_style=False).rstrip()
    includes_indented = "\n".join(f"    {line}" for line in includes.splitlines())

    answer_block = {
        "do": {"answer": {"choose": choose}},
        "expect": [
            {"kind": "equals", "key": "kind", "value": "completed"},
            {"kind": "gte", "key": "resumes", "value": 1},
            {"kind": "includes", "key": "written_files", "value": written},
            *extra_answer,
        ],
    }
    answer_yaml = yaml.safe_dump([answer_block], default_flow_style=False).rstrip()

    body = f"""\
# user story: {stage["story"]}
# Sequential delegate_pkg stage — coding-delegate dogfood.
# Static: coding_writes stubs (provisional). Live Completer is the gate.
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
      run_id: delegate-{stage["scenario"]}
      inputs:
{inputs_indented}
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
{answer_yaml}
{chr(10).join(read_steps)}
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
            "`environment.workspace: suite`, soft point `external_guidance` "
            "(choices minimal/thorough), and budget soft point `max_iterations`. "
            "List stages pass `instruction_mode: list` into "
            "`ProjectCodingLocalWork` / `build_instruction_plan`. Host "
            "`verify_runs` include `pytest: true` and `text_contains` / "
            "`text_forbids` with repair. Live mode binds "
            "`completer_as_tool_loop_complete`; static `coding_writes` are "
            "provisional until the live suite passes. MCP "
            "`MECHA_MCP_HOST=project_coding` drives the same "
            "`DurableGraphGenerator` graph (no separate suite)."
        ),
        "validation": (
            f"Harness `user_story` scenario `{scenario}.yaml` inside sequential "
            "suite `delegate_pkg` (ordered). Live eligibility: "
            "`environment.local_work: project_coding`. Do not treat static/cassette "
            "green as proof until live Completer on the suite host has passed."
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
        "id": "delegate_pkg",
        "title": "Delegate coding arcs on a shared Widget package",
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
    print(f"wrote {len(STAGES)} delegate stories + {SUITE_DIR / 'suite.json'}")


if __name__ == "__main__":
    write_all()
