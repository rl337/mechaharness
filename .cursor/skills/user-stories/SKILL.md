---
name: user-stories
description: >-
  Write and maintain persona user stories with prose narratives under
  docs/guides/user-stories.md and tests/fixtures/models/. Use when adding or
  changing library behavior, adapters, grants, lanes, judge, harness, DI,
  Agentic Recipes / graph templates, integration/live tests, cassettes, or
  when the user mentions user stories, Nubble, Fangore, Taloneth, or story
  acceptance.
---

# User stories (MechaHarness)

User stories are **documentation and acceptance tests**. Every touched
acceptance path must be exercised by a story — unit tests alone are not enough.

Library code should be **traceable to a story**: the `implementation` section
names the modules that fulfill the feature; the `validation` section names how
that story is proven.

## Single source of truth (sync owner)

| Field | Where it lives | Who may edit |
|-------|----------------|--------------|
| `id`, `persona`, `title`, `kind`, `narrative`, `implementation`, `validation`, `footnotes` | `tests/fixtures/models/**/stories/<id>/story.json` | Humans / agents editing stories |
| Persona bios + suite preamble | `tests/fixtures/models/personas.json` | Same |
| Guide body | `docs/guides/user-stories.md` | **Generator only** — never hand-edit story sections |

```bash
# After any story.json, suite.json, or personas.json change:
python scripts/generate_user_stories_md.py
python scripts/generate_user_stories_md.py --check
# Optional: bulk-regenerate suite membership from the helper map
python scripts/generate_user_story_suites.py --check
```

`run_checks.sh` / CI run `--check` and fail if the guide is stale.

## Personas

| Persona | Role |
|---------|------|
| **Nubble** | Operations / DevOps |
| **Fangore** | Application developer |
| **Taloneth** | ML engineer |

Bios live in `personas.json` and are rendered into the guide.

## Destination: persona-task YAML (`user_story`)

**Decision:** new and migrated acceptance uses `kind: user_story` —
environment → graph → steps → complete → cleanup — wrapping **product** CLI
verbs. Production CLI scripts stay verb-led; the story harness is the wrapper
that acts out the persona task. Do not add new `request.json` / `op` stories.

| Target harness | Use when |
|----------------|----------|
| **`user_story`** | Canonical acceptance. Persona walkthrough YAML; Config from `environment` only; drives `CliInstrumentor` verbs. |
| **`cli`** | Legacy script-shaped scenarios (still registered). Migrate to `user_story` when touching. Probes remain `cli` until a product verb exists. |

### Narrative litmus

`narrative` must read as an operational walk, not a capability blurb:

1. Who / goal
2. Starts the CLI host (family + backend / cassette)
3. Loads graph G (or default infer universe)
4. Performs steps S1…Sn
5. Verifies completion via events / artifacts X

If that cannot be said honestly, split the story.

### Story shape (`story.json`)

```json
{
  "id": "nubble_run_cost_events",
  "persona": "nubble",
  "title": "Record cost and inference events for every harness run",
  "kind": "user_story",
  "narrative": "He starts the CLI host… loads … performs … verifies …",
  "implementation": "Library modules/classes that fulfill the feature…",
  "validation": "Harness `user_story` scenarios `event_types.yaml` / …",
  "footnotes": []
}
```

### Fixture files

| Harness | Files |
|---------|--------|
| **`user_story` (canonical)** | `story.json` + `scenarios/*.yaml` (+ `response.json` when needed) |
| **`cli` (legacy)** | same layout; script `commands:` shape |
| **Legacy op** | `request.json` + `expect.json` — **do not create new** |

`footnotes` is **required** (use `[]` when none). Each entry needs `id`, `label`,
and `url`; `note` is optional.

### Intent check (every scenario)

Before writing or migrating YAML:

1. Read `story.json` (`narrative`, `implementation`, `validation`, `footnotes`).
2. Follow footnotes into `docs/inspiration/` and the map in `REQUIREMENTS.md`.
3. List normative claims → **one claim (or tight cluster) per** `scenarios/*.yaml`.
4. Assert that claim with hard expects — not a copy of weak legacy soft keys.
5. Grow `CliInstrumentor` / `cli_universe` only as needed for that wave.

### App harness principles

1. Story harness wraps a **real MechaHarness host** (DI Config + product verbs).
2. Scenario YAML declares the **persona task phases**; comments cite the story id
   and mirror the narrative. Product CLI scripts remain verb lists without
   `environment` / `complete`.
3. Soft points remain the UI answer seam where advice applies.
4. Hard expects only. No soft `_include` suffixes for new scenarios.
5. One story → many concise YAML files when claims diverge.
6. Gap/import probes are unit/doctest, not stories.
7. **Litmus:** about to add `_run_*` or a new `op`? Stop — add a CLI verb or
   `user_story` scenario instead.
8. **No `probe`** under `user_story` steps. Clocks belong in `environment.clock`.

### Positive-path coverage (mock / cassette)

From story harness **initialization**, instrument mock or cassette inference
so every **product positive path** is hit by ≥1 story. Refusal / deny stories
still count.

1. Set `environment.family` / `environment.backend` so Config binds the real
   harness family and Completer (ScriptedInference, cassette HTTP strategy).
2. Drive claims through product verbs in `steps[].do` — not probe-local DI.
3. Probes remain only on legacy `kind: cli` until a product verb exists.
4. `scripts/story_coverage.py` / `fail_under` gate the suite; ratchet up, never down.

### `user_story` scenario shape

```yaml
# user story: <id>
# Comment: persona starts CLI, loads graph, walks steps, verifies completion.
kind: user_story

environment:
  family: pass_through
  backend: mock          # mock | anthropic | openai_compat | …
  # clock: '2026-01-15T12:00:00Z'

graph: null              # or { recipe, bind?, durable? }

steps:
  - do:
      infer:
        prompt: Say hello.
    expect:
      - kind: nonempty
        key: text

complete:
  expect:
    - kind: includes
      key: event_types
      value: [core:inference, core:cost]

cleanup: []
```

Models: `tests/stories/scenarios/user_story_scenario.py`. Harness:
`tests/stories/harness/user_story.py`. Product verbs remain on
`MechaHarnessConfig.cli_verb_classes()`. See
[`docs/reference/cli-universe.md`](../../../docs/reference/cli-universe.md).

Live: `MECHA_STORY_BACKEND=live`, `MECHA_BASE_URL`, `MECHA_MODEL` (served id).

### Migration batches

Remaining `kind: cli` stories convert in waves — product verbs first (A–F), then
probe families after a product verb exists (P1–P10). Checklist and story ids:
[`docs/guides/user-story-migration-batches.md`](../../../docs/guides/user-story-migration-batches.md).

### Full migration program

Migrate in waves; each wave adds the smallest CLI/harness surface required:

1. Observability / one-shot infer (OBS-*) — **done**
2. Former `harness_runs` / pass-through / tool-loop / cassettes / host DI /
   judge route — **done**
3. Graph execution — **done** (`probe` + `cli_probe_classes`)
4. Durable IoC — **done** (CLI verbs; parallel harness removed)
5. Decision plane / remaining judge ops — **done** (`decision_plane` runner removed)
6. `pure_api` + context/eval library surface

When a family has zero stories left, delete its op-dispatch runner module.
When an individual `op` has zero remaining `request.json` stories, delete that
op’s `_run_*` function and `RUNNERS` entry in the same change as the migration.

### `narrative` (required)

Audience: a **non-technical project manager** who understands features, not code.

- Literal English. Keep persona names; do **not** assume dragon lore or use forge/torch metaphors.
- No CamelCase modules, Config hooks, event type keys, CLI flags, or file paths as API docs.
- Cross-refs: only other story ids in backticks (`` `story_id` ``) plus plain domain words (lane, grant, judge, cassette).
- External articles: put them in `footnotes` and optionally cite as `[^id]` in the
  narrative — **not** raw URLs in the narrative body.
- If you need a capability that has no story yet — **backfill that story first**, then cite it.

### `implementation` (required)

**Product / library functionality** that makes the story true — not the test.

- Name modules, classes, Config hooks, and behaviors in `src/mechaharness/…`.
- When the story is fulfilled by an **Agentic Recipe**, name the recipe by
  **catalog id** (for example `verify_repair`, `decision_plane`,
  `fan_out_aggregate`) so readers learn recipes as part of the implementation
  surface. Mechanism-only stories (soft points, stamping, demotion) may name
  `GraphTemplate`; pattern stories must name the recipe.
- Every shipped Agentic Recipe needs ≥1 owning story that exercises that recipe
  as the unit under test — see [`agentic-recipes`](../agentic-recipes/SKILL.md).
- When the story owns traversal, console lighting, or recipe interiors, name
  **node-component kinds** (from
  [`docs/reference/node-components.md`](../../../docs/reference/node-components.md))
  in `implementation` — see [`node-components`](../node-components/SKILL.md).
- Write so a reader can trace “this code exists because of this story.”
- Do **not** put runner kinds, soft expects, or fixture paths here (those belong in `validation`).
- New library acceptance maps to a **story id**. Local `REQUIREMENTS.md` cites
  stories (not new INF/POL codes as the primary vocabulary).

### `footnotes` (required key; may be `[]`)

External article citations for this story. Twin parity includes `footnotes`
(deep-equal). Catalog / generator `--check` enforces:

1. **Story ids unique** in the canonical set (prefer `static/fixture/v1`). Directory
   name must equal `story.json` `"id"`. Twins may reuse the same id with parity;
   they must not introduce a different story under a colliding id.
2. **Footnote `id`s unique within each story.**
3. **Footnote `id`s unique across the generated guide** (no global collisions) so
   `[^id]` markers stay stable.

Generator renders a **Footnotes** subsection per story (numbered list, or markdown
footnote defs when the narrative contains matching `[^id]` markers).

### `validation` (required)

**How the story is proven** — technical, like `implementation`, but about tests.

- Cite `Harness \`cli\` scenarios \`…yaml\`` and the hard
  expect keys / scenario stems.
- Cassette / live dual-mode notes when relevant.
- Related unit test modules under `tests/`.
- Do **not** cite new legacy `op` names for newly migrated stories.
- Inference-running scenarios (`infer`, `tool_loop`, completing `run_recipe`)
  MUST assert event observations: `event_types` / `includes` for
  `core:inference`, and token bounds via `prompt_tokens` /
  `completion_tokens` / `total_tokens` (`equals` / `gte` / `lte`).
- Graph-execution scenarios that expose `budget_spent` MUST declare a cost
  ceiling (`lte` / `equals` / `gte` / `positive` on `cost_units` or
  `budget_spent`). The harness fails the story when that expect is missing.


### `title`

Literal feature outcome (not metaphor). Must match what `narrative` claims.

## Sync rules

1. **Edit fixtures first.** Never patch `docs/guides/user-stories.md` by hand.
2. **Twin parity.** The same `id` under `static/fixture`, `openai_compat/…`, and
   `systemone/…` must share identical `title`, `narrative`, `implementation`,
   `validation`, `persona`, `kind`, and `footnotes`. Catalog validation fails
   the PR on drift.
3. **Sibling coherence.** If acceptance intent changes, update `scenarios/*.yaml`
   (or migrate off `request`/`expect`) in the same change. Narrative must not
   claim an outcome expects do not cover; `validation` must describe the proof.
4. **Regenerate every time.** After fixture edits: generate + `--check`; commit
   the regenerated guide in the same PR.
5. **Stable ids.** Renaming an `id` requires updating citations in other
   narratives and directory names.
6. **Backfill before citing.** New capability mention ⇒ new or extended story
   with full field set + twin sync + regenerate.
7. **Code ↔ story.** When adding library behavior, update (or add) the owning
   story’s `implementation`; when adding/changing tests for that path, update
   `validation`.

## Coverage rule

When you **touch** functionality in this repo:

1. Name which story id(s) exercise the change.
2. If none fit — add a **`kind: cli`** story under
   Nubble / Fangore / Taloneth — never a new legacy `op`.
3. If the owning story is still legacy op-dispatch, **migrate it to YAML** in
   the same change when practical (intent check → scenarios → delete
   request/expect).
4. Update `implementation` / `validation`; sync twins. Agentic Recipe stories
   name the catalog id in `implementation`.
5. Regenerate the guide; mention story id(s) in the PR summary.

Do **not** add skipif live modules. Offline CI must run the story suite with
**zero skips**; live is the same parametrized tests with `MECHA_STORY_BACKEND=live`.

## Suites

Suites group related story scenarios with shared `vars` / `setup` / `cleanup`
and `execution.mode` (`parallel` | `sequential`).

| Field | Purpose |
|-------|---------|
| `id`, `title`, `persona` | Catalog / guide |
| `execution.mode` | `parallel` (default) or `sequential` |
| `execution.ordered` | Only with `sequential` (shared-workspace arcs) |
| `vars` | Suite-level bindings |
| `setup` / `cleanup` | Hook names (`ensure_workspace`, …) |
| `workspace` | Optional shared root (`temp` or path); omit for parallel library suites |
| `stages[]` | `{ "story": "<id>", "scenario": "<stem>" }` |

Location:

```text
tests/fixtures/models/static/fixture/v1/suites/<suite_id>/suite.json
```

Rules:

1. Every static story scenario is in **exactly one** primary suite (coverage
   ratchet in `tests/stories/test_story_schema.py`).
2. Prefer **parallel** for independent mocks/cassettes. Use **sequential** +
   `ordered` only when stages share an arc workspace.
3. Pytest: `test_user_story_suite` runs suites; HTTP twins and any orphan
   static cases remain on `test_user_story`.
4. Membership helper (optional bulk authoring):
   `python scripts/generate_user_story_suites.py` / `--check`.
5. New stories: add scenarios, then add stages to the owning `suite.json` (or
   regenerate membership) in the same change.

Sequential example: suite id `calc_cli` (Fangore calculator arc). Stages set
`environment.workspace: suite`; the suite harness injects one shared temp root.
Author/regenerate that arc with `scripts/write_calc_cli_suite.py`.

See `docs/plans/user-story-suites.md`.

## Layout

```text
tests/fixtures/models/
  personas.json
  <family>/<model>/<version>/
    manifest.json
    stories/<story_id>/
      story.json           # kind = cli | user_story | (legacy)
      scenarios/*.yaml
      response.json        # cassette when needed
    suites/<suite_id>/
      suite.json           # stages → story + scenario
tests/stories/harness/     # cli + user_story
tests/stories/suite_*.py   # suite schema / catalog / harness
scripts/generate_user_stories_md.py
scripts/generate_user_story_suites.py
docs/guides/user-stories.md   # GENERATED
```

## Dual mode

| `MECHA_STORY_BACKEND` | Behavior |
|-----------------------|----------|
| `static` (default) | Cassettes / in-process — CI |
| `live` | Real HTTP (`MECHA_BASE_URL`, `MECHA_MODEL`, `MECHA_JUDGE_*`, …) |

Live collects HTTP twins **and** static stories that call `infer` / `judge` /
`judge_route` (see `tests/stories/live_capability.py`). Behavioral expects stay
**hard**; cassette-exact `prompt_tokens` / `completion_tokens` / `total_tokens`
equals/bounds are relaxed. Pure policy, recipe-shape, `tool_loop`, and
Anthropic-only walks stay offline.

New scenarios use **hard** expects. Wire payloads stay in `response.json` for
replay; live uses the served model id via `MECHA_MODEL`.

## Checklist (new or changed functionality)

1. Read generated `docs/guides/user-stories.md` (or regenerate first).
2. Attach to an existing story **or** draft `narrative` + `implementation` +
   `validation` under the right persona with `kind: cli`.
3. Intent-check inspiration/REQUIREMENTS; add `scenarios/*.yaml` (one claim each).
4. Grow `CliInstrumentor` / `cli_universe` only if the wave needs a new verb/node.
5. Fixture under `static/fixture/v1` first; twin for HTTP paths; twin text parity.
6. Add the new scenario as a stage on the owning `suite.json` (or regenerate
   membership via `scripts/generate_user_story_suites.py`).
7. Run `python scripts/generate_user_stories_md.py` and `--check`.
8. Confirm `tests/stories/test_story_schema.py` / twin parity / suite coverage
   will pass.
9. Unit-test edge cases separately; list them under `validation`.
10. PR summary lists story id(s) and suite id(s); no hand edits to the guide.

## Anti-patterns

```text
# BAD — hand-edit docs/guides/user-stories.md
# BAD — new request.json / op for a story (use kind: cli scenarios instead)
# BAD — twin drift (same id, different narrative/implementation/validation/footnotes)
# BAD — narrative with MechaHarnessConfig / JudgementPolicy / core:cost
# BAD — raw article URLs in narrative (use footnotes + optional [^id])
# BAD — duplicate story id or duplicate footnote id (within story or globally)
# BAD — putting runner/expect details in implementation (use validation)
# BAD — putting library design only in validation (use implementation)
# BAD — cite a capability with no story id / mint new INF-POL codes as primary
# BAD — pattern story that omits the Agentic Recipe catalog id in implementation
# BAD — ship a recipe with no owning user story
# BAD — touch a legacy story without migrating it toward YAML when practical
# BAD — soft _include expects on new CLI scenarios
# BAD — commit story.json without regenerating the guide
# BAD — static scenario with no suite stage (coverage ratchet)
# BAD — As-a bullet as the only story body
# BAD — new skipif live module for one model

# GOOD — kind: cli + scenarios/*.yaml → suite stage → generate guide → --check green
# GOOD — implementation names verify_repair (recipe) and GraphTemplate (substrate)
# GOOD — one claim per YAML; grow CLI verbs only when a story needs them
```

## Related

- [`docs/reference/cli-universe.md`](../../../docs/reference/cli-universe.md) — CLI product surface
- [`agentic-recipes`](../agentic-recipes/SKILL.md) — recipes as top-level concept
- [`project-docs`](../project-docs/SKILL.md) — defer user-story guide edits to this skill
- [`event-observability`](../event-observability/SKILL.md) — stories that assert event correlators (OBS-A*)
- [`data-driven-tests`](../data-driven-tests/SKILL.md) — case matrices (unit tests; stories use YAML)
- `.cursor/rules/unambiguous-names.mdc`, `.cursor/rules/agentic-recipes.mdc`
- `tests/stories/`
