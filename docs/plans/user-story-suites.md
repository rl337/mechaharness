# User story suites: organize, implement, migrate

## Status

**Implemented** (schema, harness, pytest, parallel thematic suites, coverage
ratchet, guide Suites section). **`calc_cli` sequential coding suite shipped**
(ordered stages + shared suite workspace).

## Goals

1. Add a **suite** level: shared setup/vars, `execution.mode` (`parallel` | `sequential`), optional `ordered`.
2. **Organize existing** static-fixture stories into thematic suites (almost all **parallel**).
3. **Migrate** discovery/CI so suite membership is first-class; free stories remain allowed during transition then ratchet to “every story in ≥1 suite.”
4. **Defer** `calc_cli` (sequential + ordered + arc workspace) until migration is green.

## What stays the same

- `story.json` + `scenarios/*.yaml` remain the narrative/claim unit.
- Twin parity, guide generation from stories, personas.
- Flat `test_user_story[case]` can remain for free stories during migration; suites add `test_user_story_suite[id]`.

## Suite model

Location (static fixture first):

```text
tests/fixtures/models/static/fixture/v1/suites/<suite_id>/suite.json
```

`suite.json` (v1 fields):

| Field | Purpose |
|-------|---------|
| `id`, `title`, `persona` | Catalog / guide |
| `execution.mode` | `parallel` (default for migrated suites) or `sequential` |
| `execution.ordered` | Only meaningful with `sequential` (calc later) |
| `vars` | Suite-level bindings merged into each stage environment |
| `setup` / `cleanup` | Declarative hooks (v1: `ensure_workspace`, no-op list OK) |
| `workspace` | Optional; omit for parallel library suites |
| `stages[]` | `{ "story": "<id>", "scenario": "<stem>" }` |

Harness:

- **Parallel suite:** expand stages to today’s independent `StoryCase` runs (same isolation as now); mark suite node parallel-safe.
- **Sequential suite:** one pytest case, shared workspace, stages in order, `@pytest.mark.serial` / xdist group (used later by `calc_cli`).
- Stage failure policy (v1): fail the suite; sequential arcs skip remaining stages with clear “prerequisite failed.”

Docs: extend `.cursor/skills/user-stories/SKILL.md` + regenerate guide with a Suites section.

## How to organize *existing* stories

Do **not** force one sequential mega-suite. Cluster by **capability** into **parallel** suites. Multi-scenario stories stay one story; each scenario is an explicit suite stage.

### Fangore (suite map)

| Suite id | `execution` | Member themes |
|----------|-------------|---------------|
| `fangore_durable_ioc` | parallel | durable_*, guidance_*, graph_guidance_yield, driver_session_resume, local_plan_resume |
| `fangore_guided_coding` | parallel | guided_coding_recipe (session, helper_run_python), instruction_todo_plan (all scenarios) |
| `fangore_decision_plane` | parallel | decision_plane_*, decision_surface_reject |
| `fangore_access_authority` | parallel | grants, capability envelope, authority gate, execution token, denial, auth epoch, soft vs hard, risk autonomy, human review |
| `fangore_job_lanes` | parallel | job_lane_* |
| `fangore_graph_executor` | parallel | graph_*, linkage/preflight, traversal, node_components, soft enter/until/one_step, budget |
| `fangore_recipes_tiling` | parallel | verify_repair, bounded_retry/repair, conversational_tool_loop, environment_repair, recipe_as_tool, namespace_tile, produce_critique, independent_review, initialize_preflight, fan_in, stop_contract, … |
| `fangore_context_memory` | parallel | context_*, derived_memory, compaction/layers/provider, observation chain, deficit |
| `fangore_host_kit` | parallel | host_kit_*, completer_flavors, config_access_policy, backend_describe_recipe, harness_* |
| `fangore_tdr_crash` | parallel | all tdr_crash_* |
| `fangore_jev` | parallel | action_safety, citation_*, context_*, req_review_*, task_route_* |
| `fangore_lifecycle_ops` | parallel | lifecycle_*, wake, wip, handoff, operation_compensation, effect_revalidation, tool freshness/effects |
| `fangore_recipe_registry` | parallel | recipe lineage/version/port/registry compose, soft evolution, template incubation |

Exact membership: checklist from `static/fixture/v1/stories/*/story.json` during migration; every story id in **exactly one** primary suite for v1.

### Nubble

| Suite id | Members |
|----------|---------|
| `nubble_observability` | run_cost_events, graph_event_correlators, trace_*, resume_cost, guidance_cost_budget, coordination_cost, efficiency_scorecard, recipe_audit_dimensions, review_audit_reconstruct |
| `nubble_routing_topology` | model_affinity, lane_load_hint, model_routing, repo_topology, topology_efficiency, environment_*, workspace_isolation, rollout_graph |

### Taloneth

| Suite id | Members |
|----------|---------|
| `taloneth_decision_eval` | fixture_judge_batch, policy_replay, shadow_*, decision_plane_shadow_compare, offline_decision_export, validator_qualification |
| `taloneth_harness_research` | insp_* experiment/eval/ablation/parity/promotion/safety/…, atk_research, cache_layout |

HTTP twins stay under model trees; suites **reference story ids** (no fixture duplication).

## Implementation order

1. **Schema + loader** — `SuiteSpec`; load `suites/*/suite.json`; validate refs; execution defaults (`parallel`, `ordered: false`).
2. **Harness** — `run_user_story_suite`; merge `vars`; setup/cleanup; parallel = isolated stage runs; sequential = shared workspace + stop on failure.
3. **Pytest** — `test_user_story_suite`; serial mark for sequential. Keep `test_user_story` until orphan ratchet is 100%.
4. **Coverage ratchet** — every static story id ∈ ≥1 suite.
5. **Migrate** — author `suite.json` files per tables above.
6. **Docs** — user-stories skill + guide Suites section + CHANGELOG.
7. **`calc_cli`** — sequential + ordered + `workspace: temp` +
   `setup: [ensure_workspace]`; stages use `environment.workspace: suite`.

## Parallel vs sequential

| Kind | When |
|------|------|
| **parallel** (default migrate) | Library catalog — independent mocks/cassettes |
| **sequential + ordered** | Shared workspace arcs — **`calc_cli`** |

`fangore_guided_coding` stays **parallel**: `session` and `helper_run_python` do not share an arc dir today.

## Sequential suite run ids (resume)

Sequential suites (`calc_cli`) persist each attempt under
`.mechaharness/suite_runs/<run_id>/` with a shared `workspace/`, `manifest.json`,
and conspicuous `RUN_ID.txt` / `BANNER.txt`. Pointers: `LATEST`, `<suite>.latest`.

| Env | Purpose |
|-----|---------|
| `MECHA_SUITE_RUN_ID` | Resume that run’s workspace + completion marks |
| `MECHA_SUITE_FROM` | Restart at stage (`story/scenario`, stem, or index); requires run id |
| `MECHA_SUITE_RUNS_DIR` | Override runs root |

## Out of scope

- Suite-level live backend beyond stage environment
- Moving story directories on disk
