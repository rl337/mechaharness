#!/usr/bin/env python3
"""Author fangore_calc_* stories + sequential calc_cli suite.json.

Reads progressive ``calc.py`` stubs from
``tests/fixtures/models/static/fixture/v1/suites/calc_cli/sources/``.

Static CI uses ``coding_write`` stubs. Live
(``MECHA_STORY_BACKEND=live``) ignores stubs and drives
``ProjectCodingLocalWork`` with a real Completer against ``MECHA_BASE_URL``.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "tests/fixtures/models/static/fixture/v1/stories"
SUITE_DIR = ROOT / "tests/fixtures/models/static/fixture/v1/suites/calc_cli"
SOURCES = SUITE_DIR / "sources"

# Required API shape — host verify_runs + workspace_read enforce this; goals must
# state it so live Completers do not ship ``__main__``-only CLIs.
CLI_SHAPE = (
    "Required API shape (non-negotiable): define both `def evaluate(expr)` and "
    "`def main(argv=None) -> int` by those exact names (main must not be only an "
    "inline `if __name__ == '__main__'` block). main reads sys.argv[1], prints the "
    "result, exits 0 on success / 1 on error / 2 on bad usage. Implement a real "
    "expression parser — do NOT use eval(), exec(), or ast.literal_eval on the "
    "user expression. You MUST call write_file with the full calc.py contents "
    "before finishing."
)

STAGES: list[dict[str, object]] = [
    {
        "story": "fangore_calc_parse_number",
        "scenario": "bootstrap",
        "source": "00_parse_number.py",
        "title": "Bootstrap a CLI that evaluates number literals",
        "goal": (
            "Create calc.py in the workspace: a CLI math calculator that for now "
            "only evaluates number literals (e.g. 42, 3.14). Do not implement "
            f"operators yet. {CLI_SHAPE}"
        ),
        "narrative": (
            "Fangore starts the CLI host with family `pass_through` and backend "
            "`mock`, loads the `guided_coding` durable graph, and grows a shared "
            "calculator workspace from an empty arc. He asks for a small command-line "
            "program that reads one expression and prints a number literal value. "
            "He answers the external guidance soft point, confirms `calc.py` on disk, "
            "and runs it on `42` and `3.14` so the bootstrap claim is proven before "
            "later stages add operators. Live mode uses a real reason model for the "
            "coding burst; static mode uses an offline write stub."
        ),
        "checks": [("42", "42"), ("3.14", "3.14")],
    },
    {
        "story": "fangore_calc_add_sub",
        "scenario": "add_sub",
        "source": "01_add_sub.py",
        "title": "Extend the calculator with addition and subtraction",
        "goal": (
            "Update existing calc.py (read it first) so left-associative + and - "
            "work on number literals, e.g. 1+2-3 → 0 and 10-4+1 → 7. Keep number "
            f"literals working. {CLI_SHAPE}"
        ),
        "narrative": (
            "Fangore continues the shared calculator arc. He asks guided coding to "
            "extend `calc.py` so left-associative addition and subtraction work "
            "(`1+2-3`) while number literals from the bootstrap stage still evaluate. "
            "He answers guidance, confirms the file, and runs regression expressions "
            "for both numbers and additive chains."
        ),
        "checks": [("42", "42"), ("1+2-3", "0"), ("10-4+1", "7")],
    },
    {
        "story": "fangore_calc_mul_div",
        "scenario": "mul_div",
        "source": "02_mul_div.py",
        "title": "Add multiplication and division with tighter precedence",
        "goal": (
            "Update calc.py so * and / bind tighter than + and -: 2+3*4 → 14, "
            "8/2*2 → 8 (left-assoc among * /). Keep prior + - and literals green. "
            f"{CLI_SHAPE}"
        ),
        "narrative": (
            "Fangore keeps the same workspace and asks for multiplication and "
            "division that bind tighter than addition and subtraction "
            "(`2+3*4`, `8/2*2`). Prior additive cases must stay green."
        ),
        "checks": [("1+2-3", "0"), ("2+3*4", "14"), ("8/2*2", "8")],
    },
    {
        "story": "fangore_calc_exponent",
        "scenario": "exponent",
        "source": "03_exponent.py",
        "title": "Add right-associative exponentiation",
        "goal": (
            "Update calc.py to add ^ as right-associative exponentiation: "
            "2^3^2 → 512, 2*3^2 → 18. Keep + - * / precedence. "
            f"{CLI_SHAPE}"
        ),
        "narrative": (
            "Fangore extends the calculator with `^` as right-associative "
            "exponentiation (`2^3^2`, `2*3^2`) without breaking earlier precedence."
        ),
        "checks": [("2+3*4", "14"), ("2*3^2", "18"), ("2^3^2", "512")],
    },
    {
        "story": "fangore_calc_grouping",
        "scenario": "grouping",
        "source": "04_grouping.py",
        "title": "Add parentheses to override precedence",
        "goal": (
            "Update calc.py so parentheses override precedence: (1+2)*3 → 9, "
            "2^(1+1) → 4. Keep ^ right-assoc and prior ops. "
            f"{CLI_SHAPE}"
        ),
        "narrative": (
            "Fangore adds grouping symbols so parentheses override precedence "
            "(`(1+2)*3`, `2^(1+1)`) while earlier operator stages still pass."
        ),
        "checks": [("2^3^2", "512"), ("(1+2)*3", "9"), ("2^(1+1)", "4")],
    },
    {
        "story": "fangore_calc_functions",
        "scenario": "functions",
        "source": "05_functions.py",
        "title": "Add common calculator functions",
        "goal": (
            "Update calc.py with call syntax fn(args) for sqrt, abs, sin, cos, tan "
            "(radians), ln, log (base 10), min, max. Examples: sqrt(9)→3, "
            "abs(-2)+1→3, min(3,1,2)→1, sin(0)→0. Keep operators and grouping. "
            f"{CLI_SHAPE}"
        ),
        "narrative": (
            "Fangore finishes the calculator arc by adding common functions "
            "(`sqrt`, `abs`, `sin`/`cos`/`tan` in radians, `ln`/`log`, `min`/`max`) "
            "composable with prior operators and grouping. The shared workspace now "
            "holds a full expression CLI."
        ),
        "checks": [
            ("(1+2)*3", "9"),
            ("sqrt(9)", "3"),
            ("abs(-2)+1", "3"),
            ("min(3,1,2)", "1"),
            ("sin(0)", "0"),
        ],
    },
]


def _indent_block(text: str, spaces: int = 6) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line else pad.rstrip() for line in text.splitlines())


def _scenario_yaml(stage: dict[str, object]) -> str:
    source = SOURCES / str(stage["source"])
    calc_src = source.read_text(encoding="utf-8").rstrip() + "\n"
    checks = stage["checks"]
    assert isinstance(checks, list)
    goal = json.dumps(str(stage["goal"]))
    verify_runs = [
        {
            "path": "calc.py",
            "text_contains": ["def evaluate", "def main"],
            "text_forbids": ["eval(", "exec("],
        },
        *[
            {
                "path": "calc.py",
                "args": [expr],
                "stdout_contains": expect_stdout,
                "exit_code": 0,
            }
            for expr, expect_stdout in checks
        ],
    ]
    verify_yaml = yaml.safe_dump(verify_runs, default_flow_style=False).rstrip()
    verify_indented = "\n".join(f"        {line}" for line in verify_yaml.splitlines())

    run_steps: list[str] = []
    for expr, expect_stdout in checks:
        run_steps.append(
            textwrap.dedent(
                f"""\
                - do:
                    run_python:
                      path: calc.py
                      args:
                      - {json.dumps(expr)}
                  expect:
                  - kind: equals
                    key: exit_code
                    value: 0
                  - kind: contains
                    key: stdout
                    value: {json.dumps(expect_stdout)}
                """
            ).rstrip()
        )

    body = f"""\
# user story: {stage["story"]}
# Sequential calc_cli stage — shared suite workspace (environment.workspace=suite).
# Static: coding_write stub. Live: real Completer ignores stub and edits calc.py.
kind: user_story
environment:
  family: pass_through
  backend: mock
  local_work: project_coding
  workspace: suite
  coding_write:
    path: calc.py
    content: |
{_indent_block(calc_src, 6)}
graph:
  recipe: guided_coding
  durable:
    controller: story
    store: memory
steps:
- do:
    start:
      run_id: calc-{stage["scenario"]}
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
    - calc.py
- do:
    workspace_read:
      path: calc.py
  expect:
  - kind: 'true'
    key: exists
  - kind: contains
    key: text
    value: def evaluate
  - kind: contains
    key: text
    value: def main
{chr(10).join(run_steps)}
complete:
  expect:
  - kind: equals
    key: exit_code
    value: 0
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
            "`environment.local_work: project_coding` and "
            "`environment.workspace: suite`. Static mode uses offline "
            "`coding_write` stubs. Live mode "
            "(`MECHA_STORY_BACKEND=live` + `MECHA_BASE_URL`) ignores stubs and "
            "binds a real OpenAI-compat Completer into "
            "`ProjectCodingLocalWork` via "
            "`completer_as_tool_loop_complete`. Product verbs "
            "`workspace_read` / `run_python` assert on-disk `calc.py` and CLI "
            "stdout for this stage's grammar plus regressions."
        ),
        "validation": (
            f"Harness `user_story` scenario `{scenario}.yaml` inside sequential "
            "suite `calc_cli` (ordered). Live eligibility: "
            "`environment.local_work: project_coding`. Suite harness asserts "
            "live HTTP POSTs when coding stages run under live backend."
        ),
        "footnotes": [],
    }


def write_all() -> None:
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
        "id": "calc_cli",
        "title": "Grow a CLI math expression calculator",
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
        json.dumps(suite, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(STAGES)} calc stories + {SUITE_DIR / 'suite.json'}")


if __name__ == "__main__":
    write_all()
