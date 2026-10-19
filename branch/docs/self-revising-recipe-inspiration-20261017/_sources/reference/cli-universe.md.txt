# CLI universe

| Surface | Value |
|---------|-------|
| Package | `mechaharness.cli_universe`, `cli_infer_runner`, `cli_instrumentor` |
| Story harness | `kind: cli` with `scenarios/*.yaml` |
| Stability | evolving (Wave 1+: grow verbs as stories migrate) |

## Role

Hand-built **concrete** capability graph for the host CLI/TUI — not a
`GraphTemplate` / Agentic Recipe. Commands are verb-led with optional params and
product defaults. Soft points stay the UI answer seam elsewhere; this graph
grows by adding hard nodes and instrumentor verbs as user stories migrate.

| Concept | Module |
|---------|--------|
| Graph factory | `build_cli_universe_graph` (`cli:infer` node) |
| Infer runner | `CliInferRunner` (reason-lane `Completer`, `core:inference` + `core:cost`) |
| Instrumentor | `CliInstrumentor` (`infer`, `set_clock`, `advance_clock`, …) |
| Event stamps | `StampingEventLog` over injectable `DateTimeService` |

Distinct from:

- **Durable generator scripts** (`durable_generator_script`) — IoC start/answer/inspect (fold into CLI later)
- **Agentic Recipes** — `GraphTemplate` soft-point catalogs (`verify_repair`, …)

## Story layout (canonical acceptance)

**All user stories are migrating here.** New acceptance is `kind: cli` +
`scenarios/*.yaml`. One story may own many concise scenarios (one claim each):

```text
stories/<id>/
  story.json
  scenarios/
    event_types.yaml
    event_timestamps.yaml
  response.json          # cassette when needed
```

YAML is CLI-shaped; `expect:` is test-only (hard equality). Cassette vs live is
harness/Config (`MECHA_STORY_BACKEND`, `MECHA_BASE_URL`, `MECHA_MODEL`), not YAML.

## Intent check

Before migrating a story, re-read `story.json` footnotes, `docs/inspiration/`,
and `REQUIREMENTS.md`. Map normative claims → scenario files; do not copy
legacy soft expects blindly. See `.cursor/skills/user-stories/SKILL.md`.

## Migration program

Convert every legacy `request.json` / `op` story onto CLI (or temporary
`durable_generator`) YAML. Each wave adds only the CLI verb or harness assert
needed:

1. Observability / one-shot infer (OBS-*) — started (`nubble_run_cost_events`)
2. Remaining harness_runs / pass-through / tool-loop / cassettes
3. Graph execution + recipe catalog
4. Decision plane / judge
5. pure_api + context/eval surface
6. Fold durable IoC into CLI when ready

When a legacy family has zero stories left, delete its op-dispatch runner.
