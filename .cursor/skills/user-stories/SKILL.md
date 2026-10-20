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
# After any story.json or personas.json change:
python scripts/generate_user_stories_md.py
python scripts/generate_user_stories_md.py --check
```

`run_checks.sh` / CI run `--check` and fail if the guide is stale.

## Personas

| Persona | Role |
|---------|------|
| **Nubble** | Operations / DevOps |
| **Fangore** | Application developer |
| **Taloneth** | ML engineer |

Bios live in `personas.json` and are rendered into the guide.

## Destination: YAML app harnesses for every story

**Decision:** convert **all** user-story acceptance tests to app-harness YAML
(CLI-shaped scripts + hard expects). Do not add new `request.json` / `op`
stories. When you touch a legacy story, migrate it in the same change (or a
tight follow-up PR in the same wave).

| Target harness | Use when |
|----------------|----------|
| **`cli`** | All acceptance. Infer, tools, recipes, durable IoC, probes, EventLog asserts, cassettes/live. Config-injected `CliInstrumentor` + growing `cli_universe`. |

Legacy op-dispatch (`pure_api`, domain runners, …) is **deprecated inventory** —
keep runners only until their stories migrate; then delete the op.

### Story shape (`story.json`)

```json
{
  "id": "nubble_run_cost_events",
  "persona": "nubble",
  "title": "Record cost and inference events for every harness run",
  "kind": "cli",
  "narrative": "PM-facing prose; may cite `other_story_id` or [^footnote-id]…",
  "implementation": "Library modules/classes that fulfill the feature…",
  "validation": "Harness `cli` scenarios `event_types.yaml` / `event_timestamps.yaml`; hard expects…",
  "footnotes": []
}
```

### Fixture files

| Harness | Files |
|---------|--------|
| **`cli` (canonical)** | `story.json` + `scenarios/*.yaml` (+ `response.json` cassette when needed) |
| **Legacy (migrating)** | `request.json` + `expect.json` — **do not create new**; remove when the story moves to YAML |

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

1. Harness is a **real MechaHarness host** (DI Config, `cli_universe`, recipes,
   durable generator) — not a pytest-shaped wrapper.
2. YAML is **CLI/host instructions** a human could scan; `expect:` is test-only.
3. Soft points remain the UI answer seam where advice applies.
4. Hard expects only (strict equality on declared keys). No soft `_include`
   suffixes for new scenarios.
5. One story → many concise YAML files when claims diverge (events vs timestamps).
6. Gap/import probes are unit/doctest, not stories.
7. **Litmus:** about to add `_run_*` or a new `op`? Stop — add a CLI verb or
   scenario instead.

### `cli` scenario shape

```yaml
# One-line claim
kind: cli
commands:
  - infer:
      prompt: Say hello.
expect:
  - kind: exactly
    key: event_types
    value: [core:access_check, core:graph_start, …]
  - kind: positive
    key: cost_units
  - kind: nonempty
    key: text
```

Verbs are a pyiv map multibind (`MechaHarnessConfig.cli_verb_classes()`).
Production catalog: `cli_host_verbs` (+ durable IoC verbs). Test delta via
`TestHarnessCliConfig` (clocks + `probe`). Story probes register on
`cli_probe_classes` and run as `probe: {path: plans/….yaml}` (preferred) or
inline `probe: {name: …}`. `run_recipe` uses `cli_recipe_adapter_classes` for
execute adapters. Catalog shape stories use `instantiate_recipe` with a
human-readable `RecipeBind` under `binds/`; lifecycle checks use `recipe_plan`
under `plans/`. Write bind/plan files for readers — comments, `summary`, and
the decisions the story cares about. `expect:` is an open assertion list
(validate kinds at load). Prefer many YAML scenarios over bag-ops; discovery =
add YAML.
See [`docs/reference/cli-universe.md`](../../../docs/reference/cli-universe.md).

Live: `MECHA_STORY_BACKEND=live`, `MECHA_BASE_URL`, `MECHA_MODEL` (served id).

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

## Layout

```text
tests/fixtures/models/
  personas.json
  <family>/<model>/<version>/
    manifest.json
    stories/<story_id>/
      story.json           # kind = cli | (legacy during migration)
      scenarios/*.yaml     # cli: CLI commands + hard expect (preferred)
      response.json        # cassette when needed
tests/stories/harness/     # cli (+ legacy until empty)
tests/stories/runners/     # deprecated op-dispatch; delete per migrated family
scripts/generate_user_stories_md.py
docs/guides/user-stories.md   # GENERATED
```

## Dual mode

| `MECHA_STORY_BACKEND` | Behavior |
|-----------------------|----------|
| `static` (default) | Cassettes / in-process — CI |
| `live` | Real HTTP (`MECHA_BASE_URL`, `MECHA_MODEL`, `MECHA_JUDGE_*`, …) |

New scenarios use **hard** expects. Wire payloads stay in `response.json` for
replay; live uses the served model id via `MECHA_MODEL`.

## Checklist (new or changed functionality)

1. Read generated `docs/guides/user-stories.md` (or regenerate first).
2. Attach to an existing story **or** draft `narrative` + `implementation` +
   `validation` under the right persona with `kind: cli`.
3. Intent-check inspiration/REQUIREMENTS; add `scenarios/*.yaml` (one claim each).
4. Grow `CliInstrumentor` / `cli_universe` only if the wave needs a new verb/node.
5. Fixture under `static/fixture/v1` first; twin for HTTP paths; twin text parity.
6. Run `python scripts/generate_user_stories_md.py` and `--check`.
7. Confirm `tests/stories/test_story_schema.py` / twin parity will pass.
8. Unit-test edge cases separately; list them under `validation`.
9. PR summary lists story id(s); no hand edits to the guide.

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
# BAD — As-a bullet as the only story body
# BAD — new skipif live module for one model

# GOOD — kind: cli + scenarios/*.yaml → generate guide → --check green
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
