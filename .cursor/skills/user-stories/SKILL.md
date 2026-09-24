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

## Personas

| Persona | Role |
|---------|------|
| **Nubble** | Operations / DevOps |
| **Fangore** | Application developer |
| **Taloneth** | ML engineer |

Bios and full narratives: [`docs/guides/user-stories.md`](../../docs/guides/user-stories.md).

## Narrative format (required)

Each story’s body is **prose** a human can relate to: scene, stakes, what
success looks like. Store it in:

1. `docs/guides/user-stories.md` (canonical for readers)
2. `tests/fixtures/models/…/stories/<id>/story.json` → field `narrative`
   (must match the guide)

**Never** use bare “As a… / I want… / So that…” bullets or checklists as the
story body. Technical mapping (kind, modules, expects) may follow the prose in
docs or live only in `request.json` / `expect.json` / runners.

`story.json` shape:

```json
{
  "id": "nubble_lane_load_hint",
  "persona": "nubble",
  "title": "The wrong torch on the wall",
  "kind": "wrong_lane_deny",
  "narrative": "Nubble is mid-shift when a paging alert fires…"
}
```

## Coverage rule

When you **touch** functionality in this repo (library, host-facing hooks,
adapters):

1. Name which story id(s) exercise the change.
2. If none fit — **add or extend** a story with a full prose narrative under the
   right persona (or introduce a persona bio in the guide first).
3. Update guide + fixture `narrative` together.
4. Mention the story id(s) in the PR summary.

Do **not** add skipif live modules. Offline CI must run the story suite with
**zero skips**; live is the same parametrized tests with `MECHA_STORY_BACKEND=live`.

`MECHA_LIVE_JUNESPARK` / `MECHA_LIVE_QWEN` / `MECHA_LIVE_JUDGE` only select live
+ a model filter for `tests/stories/` — they are not separate test files.

## Layout

```text
tests/fixtures/models/
  <family>/<model>/<version>/
    manifest.json
    stories/<story_id>/
      story.json      # persona, title, kind, narrative
      request.json
      response.json   # wire or domain reply (static replay)
      expect.json     # soft asserts (static + live)
tests/stories/        # catalog, backend, runners, parametrized tests
docs/guides/user-stories.md
```

- **`static/fixture/v1`** — in-process, model-agnostic; always CI.
- **Captured models** (`openai_compat/…`, `systemone/…`) — cassette / live twins.

## Dual mode

| `MECHA_STORY_BACKEND` | Behavior |
|-----------------------|----------|
| `static` (default) | Cassettes / in-process — CI |
| `live` | Real HTTP (`MECHA_BASE_URL`, `MECHA_JUDGE_*`, …) |

Soft expects only (non-empty text, event types, `route_selected_in`, …). Exact
wire text belongs in `response.json` for replay, not as a live text equality.

Legacy: `MECHA_LIVE_JUNESPARK` / `MECHA_LIVE_QWEN` / `MECHA_LIVE_JUDGE` → live +
model filter (`tests/stories/backend.py`).

## Checklist (new or changed functionality)

1. Read [`docs/guides/user-stories.md`](../../docs/guides/user-stories.md).
2. Attach to an existing story **or** draft prose (scene + stakes + success)
   under Nubble / Fangore / Taloneth.
3. Add/update fixture under `static/fixture/v1` first; add captured-model twin
   only if the path needs HTTP.
4. Extend `tests/stories/runners.py` if a new `kind` is required (unambiguous
   name).
5. Sync guide narrative ↔ `story.json` `narrative`.
6. Unit-test edge cases separately; the story is the acceptance path.
7. PR summary lists story id(s).

## Anti-patterns

```text
# BAD — As-a bullet as the only story body
# BAD — new skipif live module for one model
# BAD — touch AccessPolicy / judge / lanes with only unit tests
# BAD — docs narrative diverges from story.json

# GOOD — prose in docs + matching story.json; parametrized dual-mode test
```

## Related

- [`project-docs`](../project-docs/SKILL.md) — when editing `docs/guides/user-stories.md`, keep TOC and Sphinx in sync
- `.cursor/rules/unambiguous-names.mdc`
- `tests/stories/`
