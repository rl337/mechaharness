# Coding-delegate suites (development graph)

## Goal

Make MechaHarness a **reliable handoff surface** for expensive coding: Cursor (or
another driver) answers short guidance; a local `guided_coding` /
`project_coding` graph owns the token-heavy edits under **stable contracts**,
**verify/repair**, and **resumable sequential arcs**.

**Live Completer is the gate.** Static `coding_writes` / cassette greens are
provisional mirrors until the same suite passes under
`MECHA_STORY_BACKEND=live` + `MECHA_BASE_URL`.

## Suite map (minimize suites)

Three sequential coding-delegate suites — no more for the current roadmap:

| Suite | Stories | What it proves |
|-------|---------|----------------|
| **`calc_cli`** | `fangore_calc_*` (6) | Single-file CLI growth, `evaluate`/`main`, ban `eval`, resume/snapshots |
| **`counter_pkg`** | `fangore_counter_*` (4) | Multi-file package + pytest verify + CLI |
| **`delegate_pkg`** | `fangore_delegate_*` (4) | List-mode coding, thorough guidance fork, red-green, rename refactor |

Mechanism / transport stay in existing parallel suites (not new coding suites):

| Gap | Where it lives |
|-----|----------------|
| Plan classify / list mode (no coding) | `fangore_guided_coding` → `fangore_instruction_todo_plan` |
| Guidance yield smoke (NoOp local work) | `fangore_guided_coding` → `fangore_guided_coding_recipe` |
| MCP `generator_start` / `resume` | Same `guided_coding` graph via `MECHA_MCP_HOST=project_coding`; session semantics in `fangore_insp_driver_session_resume`. Dogfood: live MCP against `delegate_pkg` goals — **no fourth suite**. |
| CI diagnose → repair → local verify | `fangore_guided_coding` → `fangore_coding_ci_diagnose` (`ci_checks` / `ci_job_log`) → `fangore_coding_static_checks` (ruff/mypy `verify_runs`) → `fangore_coding_ci_repair` |
| StopContract / graph budgets | Soft point `max_iterations` on every coding stage; mechanism stories under `fangore_graph_executor` / `fangore_recipes_tiling` |
| Workspace grants / escape | `fangore_access_authority` (+ `ProjectCodingConfig` grants) |

## `delegate_pkg` stages (concrete stories)

1. **`fangore_delegate_list_bootstrap`** — `instruction_mode: list` with two todos
   (package + test); assert `mode=list` and pytest green.
2. **`fangore_delegate_guidance_thorough`** — answer soft point `thorough`; must
   write `inc()` **and** `README.md` with Usage.
3. **`fangore_delegate_red_green`** — add `test_double` + implement `double()`
   until pytest green under verify/repair.
4. **`fangore_delegate_refactor`** — rename `Widget` → `Gadget` across package,
   tests, README; forbid leftover `class Widget`.

Authoring: `suites/delegate_pkg/suite.yaml` + `stages/*.yaml` (+ optional
`sources/` / `materialize-stage-files`).

```bash
# Static (provisional)
pytest -s -q tests/stories/test_user_story_suites.py -k delegate_pkg

# Live gate (required before trusting stubs)
MECHA_STORY_BACKEND=live MECHA_BASE_URL=<openai-compat-base-url> \
  MECHA_MODEL=<served-model-id> \
  pytest -s -q tests/stories/test_user_story_suites.py -k delegate_pkg
```

## What earlier suites already cover

| Capability | Suite |
|------------|--------|
| Sequential shared workspace + stage order | `calc_cli`, `counter_pkg` |
| Live Completer (ignore coding stubs) | both |
| `verify_runs` + repair (shape + stdout / pytest) | both |
| Suite run id / snapshot / `MECHA_SUITE_FROM` | both |
| Single-file API contract | `calc_cli` |
| Multi-file package + pytest | `counter_pkg` |

## Driver graph (product)

```text
Cursor / MCP client
  → generator_start(guided_coding, goal|instructions, verify_runs, …)
  → advice_requested (external_guidance)
  → generator_resume(choice)   # minimal | thorough
  → ProjectCodingLocalWork (tools + Completer + verify_repair*)
  → completed | failed(verify_runs_failed)
```

Story suites keep that graph honest whether pytest or MCP drives them.

## Non-goals (yet)

- Replacing Cursor’s agent with MechaHarness for all edits
- Hosting Comfy / media lanes inside coding suites
- Auto-promoting live suites into default CI (live stays opt-in)
- A dedicated MCP-only story suite (transport parity, not a new arc)
