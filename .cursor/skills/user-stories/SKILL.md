---
name: user-stories
description: >-
  Write and maintain persona user stories with prose narratives under
  docs/guides/user-stories.md and tests/fixtures/models/. Use when adding or
  changing library behavior, adapters, grants, lanes, judge, harness, DI,
  integration/live tests, cassettes, or when the user mentions user stories,
  Nubble, Fangore, Taloneth, or story acceptance.
---

# User stories (MechaHarness)

User stories are **documentation and acceptance tests**. Every touched
acceptance path must be exercised by a story — unit tests alone are not enough.

## Single source of truth (sync owner)

| Field | Where it lives | Who may edit |
|-------|----------------|--------------|
| `id`, `persona`, `title`, `kind`, `narrative`, `implementation` | `tests/fixtures/models/**/stories/<id>/story.json` | Humans / agents editing stories |
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
  "id": "fangore_compound_grants",
  "persona": "fangore",
  "title": "Compose read-only and write permission packs",
  "kind": "grant_gate_write",
  "narrative": "PM-facing prose; may cite `other_story_id`…",
  "implementation": "Modules, kind, expects, runner notes…"
}
```

### `narrative` (required)

Audience: a **non-technical project manager** who understands features, not code.

- Literal English. Keep persona names; do **not** assume dragon lore or use forge/torch metaphors.
- No CamelCase modules, Config hooks, event type keys, CLI flags, or file paths as API docs.
- Cross-refs: only other story ids in backticks (`` `story_id` ``) plus plain domain words (lane, grant, judge, cassette).
- If you need a capability that has no story yet — **backfill that story first**, then cite it.

### `implementation` (required)

May name modules, classes, `kind`, soft expects, and related unit tests. This is
the technical half; keep it short.

### `title`

Literal feature outcome (not metaphor). Must match what `narrative` claims.

## Sync rules

1. **Edit fixtures first.** Never patch `docs/guides/user-stories.md` by hand.
2. **Twin parity.** The same `id` under `static/fixture`, `openai_compat/…`, and
   `systemone/…` must share identical `title`, `narrative`, `implementation`,
   `persona`, and `kind`. Catalog validation fails the PR on drift.
3. **Sibling coherence.** If `kind` or acceptance intent changes, update
   `request.json` / `expect.json` / `tests/stories/runners.py` in the same
   change. Narrative must not claim an outcome expects do not cover.
4. **Regenerate every time.** After fixture edits: generate + `--check`; commit
   the regenerated guide in the same PR.
5. **Stable ids.** Renaming an `id` requires updating citations in other
   narratives and directory names.
6. **Backfill before citing.** New capability mention ⇒ new or extended story
   with full field set + twin sync + regenerate.

## Coverage rule

When you **touch** functionality in this repo:

1. Name which story id(s) exercise the change.
2. If none fit — add or extend a story under Nubble / Fangore / Taloneth (update
   `personas.json` only if a new persona is truly required).
3. Update all twin `story.json` copies together.
4. Regenerate the guide; mention story id(s) in the PR summary.

Do **not** add skipif live modules. Offline CI must run the story suite with
**zero skips**; live is the same parametrized tests with `MECHA_STORY_BACKEND=live`.

## Layout

```text
tests/fixtures/models/
  personas.json
  <family>/<model>/<version>/
    manifest.json
    stories/<story_id>/
      story.json      # id, persona, title, kind, narrative, implementation
      request.json
      response.json
      expect.json
tests/stories/        # catalog, backend, runners, schema tests
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
2. Attach to an existing story **or** draft `narrative` + `implementation` under
   the right persona.
3. Add/update fixture under `static/fixture/v1` first; add captured-model twin
   only if the path needs HTTP — keep twin text identical.
4. Extend `tests/stories/runners.py` if a new `kind` is required (unambiguous
   name).
5. Run `python scripts/generate_user_stories_md.py` and `--check`.
6. Confirm `tests/stories/test_story_schema.py` / twin parity will pass.
7. Unit-test edge cases separately; the story is the acceptance path.
8. PR summary lists story id(s); no hand edits to the guide.

## Anti-patterns

```text
# BAD — hand-edit docs/guides/user-stories.md
# BAD — twin drift (same id, different narrative/implementation)
# BAD — narrative with MechaHarnessConfig / JudgementPolicy / core:cost
# BAD — cite a capability with no story id
# BAD — change kind without runners/expects
# BAD — commit story.json without regenerating the guide
# BAD — As-a bullet as the only story body
# BAD — new skipif live module for one model

# GOOD — edit story.json (+ twins) → generate guide → --check green
```

## Related

- [`project-docs`](../project-docs/SKILL.md) — defer user-story guide edits to this skill
- `.cursor/rules/unambiguous-names.mdc`
- `tests/stories/`
