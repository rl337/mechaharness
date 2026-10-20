# CLI universe

| Surface | Value |
|---------|-------|
| Package | `mechaharness.cli_universe`, `cli_infer_runner`, `cli_instrumentor` |
| Story harness | Canonical: `kind: user_story` (persona-task YAML wrapping verbs). Legacy: `kind: cli` script YAML. |
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

Production verbs stay lean (`infer`, `tool_loop`, `run_recipe`,
`instantiate_recipe`, `tile_recipe`, `recipe_plan`, diagnostics, judge,
durable IoC `start`/`answer`/`inspect`/`rebuild`/`list_recipes`,
`transactional_resume` for DR-10 crash-window durable coding-job resume).
Test-only clocks and the `probe` verb join via `TestHarnessCliConfig`
(`tests/stories/cli_probes`). Story probes register on `cli_probe_classes`.
Probe stories load a human-readable plan under ``plans/``
(``probe: {path: plans/….yaml}`` with ``name`` + params + optional ``summary``);
inline ``probe: {name: …}`` remains valid for tiny cases.

**Recipe parameterization** uses a human-readable
:class:`~mechaharness.recipe_bind.RecipeBind` document (story ``binds/`` or
CLI ``path:``) via ``instantiate_recipe`` — not a new verb per catalog id.
Authors list the soft decisions that matter; omitted soft points take catalog
defaults; unknown keys fail. `cli_universe` remains the host shell for infer /
durable IoC; recipe shape stories bind and expand a catalog recipe instead.

Grow `cli_universe` nodes when stories need product surface that isn’t there
yet — not one node per verb. If the graph never grows, stories aren’t covering
real host interaction.

Distinct from:

- **Agentic Recipes** — `GraphTemplate` soft-point catalogs (`verify_repair`, …)
- **Durable generator product API** — `DurableGraphGenerator` / host kit; CLI
  verbs drive the same session through the instrumentor

## Story layout (canonical acceptance)

Product CLI scripts stay verb-led (`commands:` / instrumentor). **Story
acceptance** is a separate harness wrapper: `kind: user_story` YAML with
`environment` → `graph` → `steps` → `complete` → `cleanup` that *drives*
those verbs (see `tests/stories/scenarios/user_story_scenario.py`). Legacy
`kind: cli` script scenarios remain until migrated.

One story may own many concise scenarios (one claim each):

```text
stories/<id>/
  story.json
  scenarios/
    event_types.yaml
    event_timestamps.yaml
  response.json          # cassette when needed
```

```yaml
kind: user_story
environment:
  family: pass_through
  backend: mock
graph: null
steps:
  - do:
      infer:
        prompt: Say hello.
complete:
  expect:
    - kind: exactly
      key: event_types
      value: [core:access_check, core:graph_start, …]
    - kind: positive
      key: cost_units
    - kind: equals
      key: total_tokens
      value: 5
cleanup: []
```

Inference-running verbs (`infer`, `tool_loop`, `run_recipe` that completes)
expose `prompt_tokens` / `completion_tokens` / `total_tokens` summed from
`core:inference` `usage` payloads so stories can set token ceilings with
`kind: lte`.

Graph executions expose `budget_spent` (node `cost_units` charges) and fold it
into observation `cost_units` (max of priced inference units and graph spend).
Scenarios that surface `budget_spent` must declare an `lte` / `equals` /
`gte` / `positive` expect on `cost_units` or `budget_spent`.

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
11. graph_recipes — done (recipe/template probes; runner removed)

Migration complete: story acceptance is ``kind: cli`` only.

When a legacy family has zero stories left, delete its op-dispatch runner.

## ``RecipeBind`` / ``instantiate_recipe`` (documentation surface)

Shape stories keep a human-readable bind file under ``binds/`` and a thin
scenario that loads it. The bind is part of the user-story documentation: a
reader should see the recipe id, goal, acceptance, and the soft decisions that
matter. Omitted soft points take catalog defaults; unknown soft point keys fail.

```text
stories/<id>/
  story.json
  binds/
    verify_repair.yaml      # prose comments + RecipeBind fields
  scenarios/
    verify_repair_recipe.yaml   # path: binds/… + expect
```

```yaml
# binds/verify_repair.yaml
name: verify_repair
summary: Tile verify-repair into a concrete plan with default runner kinds.
goal: ship artifact with verify gate
soft_bindings:
  produce_kind: produce
  verify_kind: verify
  repair_kind: repair
  complete_kind: complete
```

CLI hosts use the same file: ``instantiate_recipe`` with ``path:``. One verb
covers all catalog ids.

| Catalog id | Story coverage |
|------------|----------------|
| `verify_repair` | `fangore_verify_repair_recipe` |
| `environment_repair` | `fangore_environment_repair_recipe` |
| `bounded_retry` | `fangore_bounded_retry_recipe` |
| `independent_review` | `fangore_insp_independent_review` |
| `initialize_preflight` | `fangore_insp_initialize_preflight` |
| `produce_critique_refine` | `fangore_insp_produce_critique_refine` |
| `safety_eval` | `taloneth_insp_safety_eval_recipes` |
| `conversational_tool_loop` (shape) | `fangore_node_components` |
| `fan_out_aggregate` | `fangore_graph_template_soft_points` |

``tile_recipe`` loads a :class:`~mechaharness.recipe_bind.RecipeTileBind`
(``binds/*_tile.yaml``) for namespaced multi-instance composition
(`fangore_recipe_namespace_tile`).

``recipe_plan`` loads a lifecycle plan under ``plans/`` — one verb,
document-selected behavior via ``plan:``:

| ``plan:`` | Coverage |
|-----------|----------|
| `soft_evolution` | evolvable allowlist |
| `port_search` | typed IO search |
| `registry_compose` | registry-only compose |
| `registry_versions` | versions / lineage / pointer |
| `final_test_gate` | held-out promotion gate |
| `evolution_candidates` | trace → candidate → objective |
| `evolution_ownership` | host policy vs library gates |
| `recipe_as_tool` | embed child graph as tool |
| `traversal_contract` | events → traversal records |
| `demoted_refuse` | demoted template refuses expand |

``run_recipe`` remains for **execute** adapters (`harness_run`,
`backend_describe`, `conversational_tool_loop`).
