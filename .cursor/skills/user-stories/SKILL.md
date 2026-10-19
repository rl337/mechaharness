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

## Story shape (`story.json`)

```json
{
  "id": "fangore_insp_wip_backpressure",
  "persona": "fangore",
  "title": "Apply WIP back-pressure without hard-coding WIP=1",
  "kind": "pure_api",
  "narrative": "PM-facing prose; may cite `other_story_id` or [^footnote-id]…",
  "implementation": "Library modules/classes that fulfill the feature…",
  "validation": "Harness `pure_api` op `wip_policy`; expect keys…",
  "footnotes": []
}
```

`request.json` must include `"op"` (surface within that harness); remaining keys
are inputs. Example: `{ "op": "wip_policy", "max_active_nodes": 2, … }`.

`footnotes` is **required** (use `[]` when none). Each entry needs `id`, `label`, and
`url`; `note` is optional.

### `kind` = harness family (not a per-story runner)

`kind` names a **reusable story harness** under `tests/stories/harness/`
(`pure_api`, `access_authority`, `graph_execution`, `graph_recipes`,
`harness_runs`, `decision_plane`, `context_management`, `evaluation_research`,
`lifecycle_extensions`). Catalog validation rejects unknown kinds/ops.

| Want to cover… | Do this |
|----------------|---------|
| Same API, new inputs/expects | New story dir + `request`/`expect` only; **reuse** `kind` + `op` |
| New public helper, same build/call/assert shape | Register one `op` on the harness; then fixtures |
| New execution substrate (graph, recipe, HTTP, lifecycle) | Add/extend a **harness family** — never invent a per-story kind |
| Unique structural unit check | Focused `tests/test_*.py`; do not force a story |

**Litmus:** if you are about to add a new `kind` string or a new `_run_*` for one
story, stop — you need an `op` or a harness, not a story-specific entry point.

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

- Cite harness family + `op` (e.g. `Harness \`pure_api\` op \`wip_policy\``), plus
  `expect.json` asserts.
- Cassette / live dual-mode notes when relevant.
- Related unit test modules under `tests/`.
- Execution: `tests/stories/harness/` (see also [`data-driven-tests`](../data-driven-tests/SKILL.md)).

### `title`

Literal feature outcome (not metaphor). Must match what `narrative` claims.

## Sync rules

1. **Edit fixtures first.** Never patch `docs/guides/user-stories.md` by hand.
2. **Twin parity.** The same `id` under `static/fixture`, `openai_compat/…`, and
   `systemone/…` must share identical `title`, `narrative`, `implementation`,
   `validation`, `persona`, `kind`, and `footnotes`. Catalog validation fails
   the PR on drift.
3. **Sibling coherence.** If harness/`op` or acceptance intent changes, update
   `request.json` / `expect.json` / the owning harness op registry in the same
   change. Narrative must not claim an outcome expects do not cover;
   `validation` must describe the updated proof.
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
2. If none fit — add or extend a story under Nubble / Fangore / Taloneth (update
   `personas.json` only if a new persona is truly required).
3. Update `implementation` and/or `validation` as appropriate; sync twins.
   If the change promotes or ships an Agentic Recipe, ensure an owning story
   names that recipe’s catalog id in `implementation`.
4. Regenerate the guide; mention story id(s) (and recipe catalog ids when
   relevant) in the PR summary.

Do **not** add skipif live modules. Offline CI must run the story suite with
**zero skips**; live is the same parametrized tests with `MECHA_STORY_BACKEND=live`.

## Layout

```text
tests/fixtures/models/
  personas.json
  <family>/<model>/<version>/
    manifest.json
    stories/<story_id>/
      story.json      # kind = harness family; narrative fields
      request.json    # required "op" + inputs
      response.json
      expect.json
tests/stories/harness/  # reusable interpreters (kind → harness)
tests/stories/runners/  # interim domain ops for OpDispatchHarness
scripts/generate_user_stories_md.py
docs/guides/user-stories.md   # GENERATED
```

## Dual mode

| `MECHA_STORY_BACKEND` | Behavior |
|-----------------------|----------|
| `static` (default) | Cassettes / in-process — CI |
| `live` | Real HTTP (`MECHA_BASE_URL`, `MECHA_JUDGE_*`, …) |

Soft expects only. Exact wire text belongs in `response.json` for replay.

## Checklist (new or changed functionality)

1. Read generated `docs/guides/user-stories.md` (or regenerate first).
2. Attach to an existing story **or** draft `narrative` + `implementation` +
   `validation` under the right persona.
3. Add/update fixture under `static/fixture/v1` first; add captured-model twin
   only if the path needs HTTP — keep twin text identical.
4. Extend `tests/stories/runners.py` if a new `kind` is required (unambiguous
   name); reflect it in `validation`.
5. Run `python scripts/generate_user_stories_md.py` and `--check`.
6. Confirm `tests/stories/test_story_schema.py` / twin parity will pass.
7. Unit-test edge cases separately; list them under `validation`.
8. PR summary lists story id(s); no hand edits to the guide.

## Anti-patterns

```text
# BAD — hand-edit docs/guides/user-stories.md
# BAD — twin drift (same id, different narrative/implementation/validation/footnotes)
# BAD — narrative with MechaHarnessConfig / JudgementPolicy / core:cost
# BAD — raw article URLs in narrative (use footnotes + optional [^id])
# BAD — duplicate story id or duplicate footnote id (within story or globally)
# BAD — putting runner/expect details in implementation (use validation)
# BAD — putting library design only in validation (use implementation)
# BAD — cite a capability with no story id / mint new INF-POL codes as primary
# BAD — pattern story that omits the Agentic Recipe catalog id in implementation
# BAD — ship a recipe with no owning user story
# BAD — change kind without runners/expects + validation update
# BAD — commit story.json without regenerating the guide
# BAD — As-a bullet as the only story body
# BAD — new skipif live module for one model

# GOOD — edit story.json (+ twins) → generate guide → --check green
# GOOD — implementation names verify_repair (recipe) and GraphTemplate (substrate)
```

## Related

- [`agentic-recipes`](../agentic-recipes/SKILL.md) — recipes as top-level concept
- [`project-docs`](../project-docs/SKILL.md) — defer user-story guide edits to this skill
- [`event-observability`](../event-observability/SKILL.md) — stories that assert event correlators (OBS-A*)
- `.cursor/rules/unambiguous-names.mdc`, `.cursor/rules/agentic-recipes.mdc`
- `tests/stories/`
