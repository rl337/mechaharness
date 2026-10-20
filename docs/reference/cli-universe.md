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
| Instrumentor | Config-injected `CliInstrumentor`; verbs via `cli_verb_classes` map multibind |
| Recipe adapters | `cli_recipe_adapter_classes` → `Dict[str, CliRecipeAdapter]` for `run_recipe` |
| Assertions | Open `cli_assertion_classes` list (`kind` / `key` / `op`-like fields) |
| Event stamps | `StampingEventLog` over injectable `DateTimeService` |
| Event tap | `tapping_event_log` on the blessed executor path (HF-05) |

Production verbs stay lean (`infer`, `tool_loop`, `run_recipe`, diagnostics,
judge, durable IoC `start`/`answer`/`inspect`/`rebuild`/`list_recipes`).
Test-only clocks and the `probe` verb join via `TestHarnessCliConfig`
(`tests/stories/cli_probes`). Story probes register on `cli_probe_classes`.

Grow `cli_universe` nodes when stories need product surface that isn’t there
yet — not one node per verb. If the graph never grows, stories aren’t covering
real host interaction.

Distinct from:

- **Agentic Recipes** — `GraphTemplate` soft-point catalogs (`verify_repair`, …)
- **Durable generator product API** — `DurableGraphGenerator` / host kit; CLI
  verbs drive the same session through the instrumentor

## Story layout (canonical acceptance)

**All user stories migrate here.** Acceptance is `kind: cli` +
`scenarios/*.yaml`. One story may own many concise scenarios (one claim each):

```text
stories/<id>/
  story.json
  scenarios/
    event_types.yaml
    event_timestamps.yaml
  response.json          # cassette when needed
```

```yaml
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

Durable IoC sessions use a scenario-level `durable:` block and per-command
`expect` / `expect_error`. Cassette vs live is harness/Config
(`MECHA_STORY_BACKEND`, `MECHA_BASE_URL`, `MECHA_MODEL`), not YAML.

Discovery = add a YAML under `scenarios/`. Prefer few reusable verbs + many
scenario files over bag-ops and per-test Python.

## Intent check

Before migrating a story, re-read `story.json` footnotes, `docs/inspiration/`,
and `REQUIREMENTS.md`. Map normative claims → scenario files; do not copy
legacy soft expects blindly. See `.cursor/skills/user-stories/SKILL.md`.

## Migration program

Convert every legacy `request.json` / `op` story onto `kind: cli` YAML. Each
wave adds only the CLI verb, probe, or universe node needed:

1. Observability / one-shot infer (OBS-*) — done
2. Former harness_runs / pass-through / tool-loop / cassettes / host DI /
   judge route — done
3. Graph execution — done (test probes + `probe` verb)
4. Durable IoC — done (CLI verbs; parallel harness removed)
5. Decision plane / remaining judge ops — done (`decision_plane` runner removed)
6. pure_api — done (library probes; runner removed)
7. context_management — done (library probes; ``includes``/``gte`` asserts)
8. evaluation_research — done (library probes; runner removed)
9. lifecycle_extensions — done (tool/graph lifecycle probes; runner removed)
10. access_authority — done (grant/authority probes; ``contains`` asserts)
11. graph_recipes

When a legacy family has zero stories left, delete its op-dispatch runner.
