# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
