# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Customer-facing agent skills** under `agent-skills/` (`use-mechaharness`,
  `mechaharness-observability`, `mechaharness.mdc`) plus
  [Agent skills for your project](docs/guides/agent-skills.md) with GitHub raw
  links on `main`, and [Host integration requirements](docs/requirements/host-integration.md)
  (HOST-01..07). Maintainer requirement: keep them in sync when public host
  APIs / correlators / promote guidance change (see `project-docs` skill).
  Docs index has a **Downstream consumers** section.

- **Dots / personal-agent safety primitives:** `CapabilityEnvelope` execution-token
  fields (`principal`, `expires_at`, `trust_origin`, `authorization_epoch`) with
  attenuation-only `narrow()`; `ToolPhase` (`observe` / `prepare` / `execute`)
  on `Tool` and `OperationContract`; authorization epoch persisted on graph
  checkpoints and checked on `GraphExecutor.run(resume=True)`;
  `ToolResult` provenance/freshness fields + `tool_result_freshness`;
  `effect_revalidation`, `AuthorityGate`, `DenialStore`, `CrossTaskIsolationGuard`;
  `HandoffRecord` `goals` / `exclusions` / `verdict`.
- **Self-revising recipe substrate:** `GraphTemplateRegistry` versions, active
  pointer, `promote` / `rollback`, lineage, evaluation attachments, and
  `composition_violations`; `SoftPoint.evolvable` allowlist; Agentic Recipe
  `produce_critique_refine`.
- **Alerts, correction debt, conflict checkpoints (phase 4):**
  `AlertEscalationPolicy` (once/log → repeated/surface → persistent/propose,
  deterministic); `SpecificationDebtRecord` / `SpecificationDebtLedger` /
  `capture_correction` (schema only; hosts generate tests) with optional
  `PromotionRecord.record_id`; `decision_conflict_checkpoint` neighbor-revisit
  helpers over `concurrent_write_conflicts` (no second CR engine).
- **Eval, evolution, safety, port search (phase 5):** held-out final-test gate
  (`require_held_out_final_test`, `FinalTestGateError`) mandatory on
  `ResearchLab.promote` when `held_out_protected` and available as
  `GraphTemplateRegistry.promote_with_final_test`; `recipe_evolution`
  (trace summaries → registry-bounded soft-binding candidates → objective
  selection, no model calls); Agentic Recipe `safety_eval`;
  `GraphTemplate.io_contract` and `recipe_port_search.search_compatible_recipes`
  (catalog ids only).
- **Audit and ownership hooks (phase 6):** optional `recipe_id`,
  `recipe_version`, `freshness_summary`, approval / denial / effect ids on
  `DecisionRecord` and `TraceEnvelope` (+ `policy_revision`); `ReviewAuditRecord`
  and `summarize_recipe_audit`; `summarize_freshness`;
  `MechaHarnessConfig.get_recipe_promotion_policy()` and
  `get_evolution_campaign_hooks()` (no-op defaults, DI-first).

- **Inspiration surface consistency pass:**
  - *Observability:* `GraphExecutor` merges `graph_id`, `graph_goal`,
    `recipe_id` / `recipe_version` / `recipe_instance_id`, `authorization_epoch`
    (and `live_authorization_epoch`), and nested `parent_run_id` / `nest_depth`
    into every `core:graph_*` lifecycle event; `GraphExecutor.run(parent_run_id=)`;
    `mechaharness.event_correlators` (`graph_trace_context`,
    `project_node_attempt_rows`); `DecisionRecord` / `TraceEnvelope` gain matching
    `graph_id` / `authorization_epoch` fields. Contract:
    `docs/requirements/event-analytics-schema.md` (OBS-A01..A06) and the
    `event-observability` skill.
  - *Host wiring:* `MechaHarnessConfig.get_authority_gate()`, `get_denial_store()`,
    `get_tool_result_freshness_policy()`; `host_kit.host_authority_gate` /
    `host_denial_store`; `mechaharness.host_apis` re-export catalog;
    `promote_recipe(..., hooks=)` calls `EvolutionCampaignHooks.on_promotion`
    after a successful pointer move; `GraphTemplateRegistry.search_compatible`.
  - *Shared helper:* `CapabilityEnvelope.authority_issue` is now the single source
    of envelope reason codes for `AuthorityGate` and `revalidate_before_effect`.

### Changed

- **Module layout (shims keep old imports working):** `isolation/` package
  (`isolation_contract`, `workspace_isolation`, `cross_task_isolation`),
  `recipe_lifecycle/` package (`recipe_evolution`, `recipe_promotion_policy`,
  `evolution_campaign_hooks`, `recipe_port_search`); `tool_phase` folded into
  `operation_registry`, `specification_debt` into `rule_promotion`,
  `review_audit` into `decision_log`; `graph_template` shim now re-exports the
  full `graph_templates` surface (`ProduceCritiqueRefineTemplate`,
  `SafetyEvalTemplate`, ...).
- **Story hygiene:** removed native/insp twin stories
  (`fangore_tool_gating`, `fangore_consequence_risk_scale`,
  `fangore_sparse_advisor_consult`, `fangore_verification_outcome_gate`,
  `taloneth_harness_experiment_retire`, `fangore_insp_capability_envelope`)
  keeping one story per concept with the richer implementation text; dead
  `inspiration_delta_contract` runner removed; `tests/stories/runners.py` split
  into a `tests/stories/runners/` package of domain modules with a thin
  `run_story` dispatcher; new story `nubble_graph_event_correlators`; deleted
  eight 5–9 line unit tests that only duplicated insp stories.
- `ResearchLab.promote` now requires `final_test=` (a passing held-out
  `EvaluatorResult`) unless the `EvalProtocol` sets `held_out_protected=False`.

## [0.4.1] — 2026-10-14

Node components, recipe CLI/SVG render, and pyiv catalog multibinds (#26).
Patch tip auto-bumped to `0.4.1` before this PyPI publish.

### Added

- **Node components** (`mechaharness.node_component`): queryable sub-node
  elements that must render within a parent graph node; kinds project existing
  events / soft points / nest / stop / budget / effects. Traversal projector
  and `embed_recipe_as_tool` (HF-08). Docs:
  `docs/reference/node-components.md`,
  `docs/requirements/dynamic-tool-graph.md`; June HF inspiration + map.
- **HF-05:** `host_graph_executor(event_log=)` and `tapping_event_log` /
  `TappingEventLog` for blessed-path event taps.
- **HF-07:** Agentic Recipe `conversational_tool_loop` +
  `ConversationalToolLoopRunner` expanding `tools.subgraph` rounds.
- Harness emits enrich `turn_start` / `inference` / `tool_call` /
  `tool_result` with `parent_node_id` and `component_id` for traversal.
- Stories: `fangore_host_kit_event_tap`, `fangore_node_components`,
  `fangore_traversal_contract`, `fangore_harness_tool_loop_graph`,
  `fangore_conversational_tool_loop`, `fangore_recipe_as_tool`,
  `fangore_harness_run_recipe`, `fangore_backend_describe_recipe`.
- CLI `recipes` group: `list` / `show` / `render` / `run`. `render` writes an
  SVG from `recipe_diagram` (ER field tables, harness loop containers,
  serpentine interiors, fan-out/fan-in stack bands) with explanations below;
  built on node components + graph structure (not Mermaid).
- Agentic Recipes `harness_run` and `backend_describe` (CLI `run` /
  `describe` library paths) with recipe runners.
- Agent guidance: `.cursor/skills/node-components/SKILL.md`; agentic-recipes
  skill/rule require declaring node components on new recipes.

### Changed

- Floor **pyiv ≥ 0.4.3** (catalog introspection / `contribute_map`).
- Agentic Recipe / backend / harness **membership** is a pyiv map multibind:
  `graph_template_classes()` / `inference_classes()` / `harness_classes()` →
  `contribute_map` + `catalog_keys`. `GraphTemplateRegistry` is injected from
  the `GraphTemplate` map (hosts extend via class-map hooks, not a second list).

## [0.4.0] — 2026-10-11

Host kit cut (#25). Merge tip auto-bumped to `0.4.0` before this PyPI publish.

### Added

- Host kit (`mechaharness.host_kit`): `host_graph_executor()` builds a
  Config-injected `GraphExecutor` with runners + optional SQLite durability;
  `SubmitOnceEffectfulRunner` covers the common submit-once / complete-on-accept
  / never-silent-redispatch effect pattern; `effectful_external_handle()` reads
  the recorded handle from a `GraphResult` without scraping node maps by hand.
  Owning story `fangore_host_kit_submit_once`; pydoc doctests +
  `tests/fixtures/host_kit/` matrix; DI guide host-kit section.

## [0.3.2] — 2026-10-10

Agentic Recipes / typed decision-plane cut (#23) plus Jev typed-judgment
domain stories (#24). GitHub tagged `v0.3.2` from the merge tip before this
PyPI publish.

### Added

- **Agentic Recipes** as a top-level product concept on the `GraphTemplate`
  substrate: composition helpers (`instance_key`, `tile`), catalog docs, and
  requirements in `docs/requirements/recipes-and-decision-plane.md`.
- Reference recipes `decision_plane` and `bounded_retry`, plus owning stories
  for `verify_repair`, `environment_repair`, and recipe namespace tiling.
- `decision_plane_runtime`: structured projection, batched typed questions,
  code-owned policy with escalation, shadow compare, evaluation telemetry,
  `assemble_context_within_budget`, and `action_question_id` routing.
- Jev typed-judgment inspiration + requirements map, with Fangore domain
  stories: `fangore_jev_citation_check`, `fangore_jev_context_picker`,
  `fangore_jev_requirements_review`, `fangore_jev_task_router`,
  `fangore_jev_action_safety`.

## [0.3.1] — 2026-10-06

PyPI cut of the 0.3.0 library (GitHub also tagged `v0.3.0` before auto-bump
raced the publish).

## [0.3.0] — 2026-10-06

Evaluation/rollout provenance cut inspired by FineEnvs multi-harness RL,
plus transactional durable resume and WalkingLabs eval substrate.

### Added

- FineEnvs `MH-MHRL-*` library surfaces: `HarnessFingerprint`,
  `EvaluationOutcome`, `ObjectivePolicy`, run parity, experiment lineage,
  `RolloutGraph`, trace reconciliation, eval matrix, cross-harness failure
  taxonomy, `InferenceCapture` + linkage preflight, learning export packs,
  experiment dimensions, exposure/discriminative telemetry, and efficiency
  scorecards. Map: `docs/inspiration/fineenvs-mh-mhrl-requirements-map.md`.
- Transactional durable graph resume: injectable `CheckpointStore` seam,
  `SqliteCheckpointStore` reference backend, opt-in `EffectfulGraphNodeRunner`
  with effect intent/acceptance/reconciliation, and crash-injection probes.
  Story: `fangore_transactional_durable_resume`. Requirements:
  `docs/requirements/transactional-durable-resume.md`. Module doctests (and
  Sphinx API pages) document Config wiring and SQLite restart usage;
  pytest runs `--doctest-modules` over `src/mechaharness`.
- WalkingLabs / eval-research inspiration primitives and persona stories
  (trace envelope, claims/evaluators/trials, context layers, WIP/fan-in,
  and related surfaces). Map:
  `docs/inspiration/walkinglabs-eval-requirements-map.md`.

### Changed

- Rename inference backend `junespark` → `openai_local` (same OpenAI-compat
  client, no baked-in `base_url`; set `MECHA_BASE_URL`). Live story shorthand
  is `MECHA_LIVE_OPENAI_COMPAT`. Guide: `docs/guides/openai-local.md`.

## [0.2.0] — 2026-09-30

Inspiration-aligned library cut for client orchestrators (graph templates,
budgets, linkage, and related primitives).

### Added

- Parameterized `graph_templates` package (fan-out/aggregate, verify/repair,
  independent review, environment repair) with soft points, provenance stamp,
  and demotion; reference docs under `docs/reference/graph-templates/`.
- `BudgetPolicy` / `Budget` with soft wind-down and hard fail; required on
  `GraphExecutor.run`; nested subgraph spend rolls into the shared ledger.
  Stories: `fangore_insp_graph_budget`, `fangore_insp_budget_subgraph_rollup`.
- Pre-exec `LinkageResolver`, `StopContract`, capability envelopes, context
  providers, verification / delegation / advisor policies, consequence scaling,
  harness experiments, instruction gotchas, and failure attribution.
- Inspiration requirements map and persona stories covering reqs 1–19.
- Same-lane Completer / JudgeProvider **flavors** via
  `MechaHarnessConfig.completer_bindings()` / `judge_bindings()` (`Named` tag
  sets) and host `Annotated[T, Named|Matched]` constructor params. Story:
  `fangore_completer_flavors`.

### Changed

- **pyiv ≥ 0.4.2** — floor bumped for `Named` / `Matched` / `Key` and
  `Annotated[...]` constructor injection. Constructor injection for
  harness/strategy; hosts must subclass `MechaHarnessConfig` (or use `run()`).
  `AbstractHarness` requires injectable deps; `HarnessConfig.subagent_tools`
  replaces the harness kwarg. `InMemoryAccessControl` /
  `InMemoryCostAccountant` require `event_log` (and policy for access).

### Fixed

- Install `eval_type_backport` on all Python versions so CI (3.12) and the CLI
  can import `mechaharness.di` (previously gated behind `python_version < '3.10'`).
- Normalize PEP 604 optional `Named`/`Matched` constructor hints for pyiv on
  Python 3.12; stop injecting `GraphExecutor.fingerprint_parts` (GenericAlias
  is not a concrete optional type).

## [0.1.2] — 2026-09-25

PyPI cut of the #12 requirements-addendum library (GitHub also tagged `v0.1.1`
for the intermediate TestPyPI upload; production skipped that number after
auto-bump raced the publish).

### Added

- REQUIREMENTS.md addendum incorporation: decision plane, convergence, context
  experiments, graph resume/fan-in, validator qualification, OBS export/metrics,
  ATK-style research; host track generalized to a nameless local inference source
- Library implementations: `OperationContract`, `ConvergenceGuard`, decision
  surfaces, shadow decision-backend reports, context compiler / derived memory /
  topology / cache layout, offline decision export, topology metrics, validator
  qualification, hierarchical fan-in
- Persona user stories as acceptance vocabulary (Nubble / Fangore / Taloneth),
  including gap stories for tool gating, human review, repair loops, and related
  paths; story `footnotes` and generated guide sync

### Changed

- Keep `docs/adr/` and `REQUIREMENTS.md` local-only (gitignored; not published)
- Story acceptance is story-id primary; former INF/POL codes retired to local
  archaeology mapping

## [0.1.0] — 2026-09-25

First public library cut: DI-first agent harness with native lanes, cost on the
run path, built-in EventLog, judge/decide outcomes, and persona user stories.

### Added

- **pyiv DI** — `MechaHarnessConfig` / `SettingsConfig`; hosts subclass hooks
  (`get_inference_class`, `get_harness_class`, `get_access_policy`, judge
  connection/provider). OpenAPI `RunRequest` / `run()` remains the non-DI facade
- **EventLog** — namespaced, host-extendable event types; queryable in-memory /
  logging logs; harness lifecycle, inference, tools, cost, and access checks
- **Cost** — Ability units, `CostAccountant`, `core:cost` on harness runs
- **Access** — deny-by-default grants, `AccessPolicy`, `CompoundPolicy` composition,
  `AccessControl` / Config `get_access_policy()`
- **Harness families** — `pass_through`, `tool_loop`, `react`, OpenAI/Anthropic
  tool families on the shared EventLog + cost path; Completer nesting
- **Lanes** — `InferenceEnvironment.active_lane()` (`reason` / `judge` / `media`);
  wrong-lane errors name operator load hints
- **Judge** — typed `judge()` → `Judgement` (signals); `JudgementPolicy` /
  `decide()` verdicts; System One adapter; injectable `APIConnectionConfig` /
  `SimpleHttpConnectionConfig.from_env` (`MECHA_JUDGE_*`); outcomes
  `Completion` / `Judgement` / `Generation`
- **Phase 1–5 scaffolds** — routing, graph, research, context experiments,
  operation registry, decision log
- **Persona user stories** — Nubble / Fangore / Taloneth prose narratives;
  dual-mode static cassettes (CI, zero skips) / live via `MECHA_STORY_BACKEND`
- **Docs site** — Sphinx + Pages at https://rl337.org/mechaharness/; founding
  principles on the home page; packaging, Trusted Publishing, and auto version bump

### Changed

- `junespark` backend no longer ships a private LAN `base_url` default; set
  `MECHA_BASE_URL`
- Settings stays slim: judge HTTP knobs bind on `APIConnectionConfig`, not as a
  provider bag on `Settings`

### Security

- Purged historical `REQUIREMENTS.md` (host LAN inventory) from git history prior
  to public release
