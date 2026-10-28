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
| Prose + runnable walk | `suites/<suite>/stages/<nn>_<slug>.yaml` | Humans / agents |
| Suite meta (no stages list) | `suites/<suite>/suite.yaml` | Same |
| Persona bios + suite preamble | `tests/fixtures/models/personas.json` | Same |
| Generated `suite.json` | under each suite dir | **`sync-suites` only** |
| Guide body | `docs/guides/user-stories.md` | **`sync-guide` only** |

```bash
# After any stage YAML, suite.yaml, or personas.json change:
python -m tests.stories.commands sync-suites
python -m tests.stories.commands sync-guide
python -m tests.stories.commands sync-suites --check
python -m tests.stories.commands sync-guide --check
# Optional: rebuild coding files.json from suite sources/
python -m tests.stories.commands materialize-stage-files
```

`run_checks.sh` / CI run `--check` and fail if suites or the guide are stale.

## Personas

| Persona | Role |
|---------|------|
| **Nubble** | Operations / DevOps |
| **Fangore** | Application developer |
| **Taloneth** | ML engineer |

Bios live in `personas.json` and are rendered into the guide.

## Destination: persona-task YAML (`user_story`)

**Decision:** acceptance uses `kind: user_story` — environment → graph → steps →
complete → cleanup — wrapping **product** CLI verbs. Production CLI scripts stay
verb-led; the story harness is the wrapper that acts out the persona task.

### Narrative litmus

`narrative` must read as an operational walk, not a capability blurb:

1. Who / goal
2. Starts the CLI host (family + backend / cassette)
3. Loads graph G (or default infer universe)
4. Performs steps S1…Sn
5. Verifies completion via events / artifacts X

### Stage YAML shape (prose + runnable)

One file under `suites/<suite_id>/stages/`:

```yaml
id: fangore_calc_parse_number
suite: calc_cli
persona: fangore
title: Bootstrap a CLI that evaluates number literals
narrative: …
implementation: …
validation: …
footnotes: []
kind: user_story
environment:
  family: pass_through
  backend: mock
  local_work: project_coding   # when coding
  filesystem:
    type: suite                # suite | temp | path
    contents: 010_….files.json # optional breakout seed files
graph:
  recipe: guided_coding
  durable: { controller: story, store: memory }
steps: […]
complete: { expect: […] }
cleanup: []
```

Former multi-scenario `story.json` groups are **suites or differentiated stages**
(distinct `id` / title). Do not share one prose blob across many runnables.

## Suites

| Field | Purpose |
|-------|---------|
| `id`, `title`, `persona` | Catalog / guide (`suite.yaml`) |
| `execution.mode` | `parallel` (default) or `sequential` |
| `execution.ordered` | Legacy flag; **order comes from stage filenames** |
| `vars` / `setup` / `cleanup` | Suite hooks (`ensure_workspace`, …) |
| `workspace` | Shared root for sequential (`temp` or path) |
| `sources` | Optional tree for `materialize-stage-files` |

Stage **order** = lexicographic `stages/*.yaml` names (`010_`, `015_`, `020_`).
`sequential` means shared workspace + fail-fast — not a separate ordered list.

Rules:

1. Every static stage is in exactly one suite (directory membership).
2. Prefer **parallel** for independent mocks/cassettes. Use **sequential** when
   stages share an arc workspace (`filesystem.type: suite`).
3. Pytest: `test_user_story_suite`; HTTP twins remain on `test_user_story`.

Sequential coding-delegate examples: `calc_cli`, `counter_pkg`, `delegate_pkg`.
See `docs/guides/coding-delegate-suites.md`.

## Layout

```text
tests/fixtures/models/
  personas.json
  static/fixture/v1/suites/<suite_id>/
    suite.yaml
    suite.json              # GENERATED
    stages/010_<slug>.yaml  # prose + runnable
    stages/010_<slug>.files.json  # optional
    assets/<story_id>/      # binds/, plans/, response.json, …
    sources/                # optional golden trees
  <family>/<model>/<version>/stories/<id>/scenarios/*.yaml  # HTTP twins
tests/stories/commands/     # pyiv CLICommand tools
docs/guides/user-stories.md # GENERATED
```

## Dual mode

| `MECHA_STORY_BACKEND` | Behavior |
|-----------------------|----------|
| `static` (default) | Cassettes / in-process — CI |
| `live` | Real HTTP (`MECHA_BASE_URL`, `MECHA_MODEL`, `MECHA_JUDGE_*`, …) |

Live collects HTTP twins **and** static stories that call `infer` / `judge` /
`judge_route` (see `tests/stories/live_capability.py`). Behavioral expects stay
**hard**; cassette-exact token equals/bounds are relaxed.

## Checklist (new or changed functionality)

1. Read generated `docs/guides/user-stories.md` (or regenerate first).
2. Add or edit `suites/<suite>/stages/<nn>_<slug>.yaml` (prose + walk).
3. Intent-check inspiration/REQUIREMENTS; one claim per stage.
4. Grow `CliInstrumentor` only if a new product verb is required.
5. Fixture under `static/fixture/v1` first; twin for HTTP paths.
6. Run `python -m tests.stories.commands sync-suites` and `sync-guide` (+ `--check`).
7. Confirm `tests/stories/test_story_schema.py` will pass.
8. Unit-test edge cases separately; list them under `validation`.
9. PR summary lists story id(s) and suite id(s); no hand edits to the guide.

## Anti-patterns

```text
# BAD — hand-edit docs/guides/user-stories.md
# BAD — suite membership maps in Python
# BAD — story.json + separate scenario YAML (retired)
# BAD — docs/plans/ checked in (local-only / gitignored)
# GOOD — stage YAML under suites/<id>/stages/; sync via pyiv commands
```
