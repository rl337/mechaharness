# Cursor execution plan: Gastronomic guided development

**Status:** M0–M6 + comparison protocol + offline late-stage e2e + arm-A suite
timing→trial harness landed. Live arm B remains **`not_run`** until gastronomic
execute can drive Completer coding comparable to `guided_coding` (never
fabricate results).
**Repository:** `rl337/mechaharness`
**Architecture and rulings:** [gastronomic-guided-development.md](gastronomic-guided-development.md)
**Primary target:** A read-only `workspace_discovery` vertical slice whose two inference calls communicate through a durable WalkBag, with bounded snapshot-bound inspection tools.
**Secondary target:** Extend that foundation into the full gastronomic guided development composition after the vertical slice is green.
**Canonical bag-checkpoint story:** `tests/fixtures/models/static/fixture/v1/suites/fangore_bag_inference_continuity/` (inspiration copies under `docs/inspiration/fixtures/` are retired references only).

## Instructions to the Cursor agent

Implement this plan in dependency order. Inspect the real implementation and repository Cursor skills before editing; **do not treat the example YAML, paths, or types here as existing syntax**. Write small, independently reviewable commits, and post test results and remaining gaps in the PR. Do not silently weaken assertions or create tests that simply mock the behavior under test.

**Non-negotiable architecture:**
- `WalkBag` is the graph's live state transport, using existing registers `in/out/acc/ctx/ask/ans/err`. Nested structured values are allowed, but reads and writes are declared. Do not use sibling `GraphNode.payload` as the inter-node data bus.
- Hard nodes use deterministic code outside inference context. General inference nodes freeze the bag once **per invocation**, compile a bounded `ContextSpec` internally, and may perform authorized read-only tool calls against that same immutable snapshot. A new inference invocation obtains a new snapshot, so it can observe previous nodes' published results.
- Judges are distinct model-backed nodes: bounded fixed input, typed verdict/abstention, **no model-initiated tool calls by default**. Graph-level nodes gather missing evidence.
- An inference output is not a source fact. Validate file/symbol/span claims against recorded workspace evidence before publishing a verified inventory.
- Persist bag and graph state together at every checkpoint. Nested graph bags are isolated with explicit input/output mappings.
- `workspace_discovery` cannot modify the target workspace. Success includes a well-supported `not_found`; insufficient coverage is `inconclusive`.
- Do not modify the existing `guided_coding` recipe as a shortcut. Preserve it as the benchmark control. Reuse existing graph, inference, tool, budget, access, transcript, and user-story primitives.

### Actual repository findings to account for

Verified on the target branch before drafting this plan:

1. `src/mechaharness/walk_bag.py` now has path get/put, `serialize`/`deserialize`, staged writes, and deep snapshot; `snapshot()` remains shallow for in-process views.
2. `ExecutionGraph.walk_bag` holds the serialized bag; `GraphExecutor` syncs before checkpoint saves and hydrates `GraphRunContext.bag` on resume.
3. `src/mechaharness/cli_infer_runner.py` still supports legacy `prompt`/`system`
   one-shots. Bag-aware nodes pass `payload.context` (`ContextSpec`): freeze bag →
   compile → Completer → publish to `response.writes`. `last_model_inputs` records
   included/omitted paths and continuity flags for story observation.
4. `src/mechaharness/context_spec.py` is the deterministic bag→messages compiler
   (`freeze_bag_snapshot` / `compile_context_spec` / `publish_response_to_bag`).
   `context_pack_runner.py` remains a separate RAG packing path.
5. `GraphWalkVerb` registers compute (`bag_put`/`bag_require`) and
   `infer`/`cli:infer` via `CliInferRunner`, returning `bag` and `model_inputs`
   observations. Optional `payload.completion` scripts Completer text for mock stories.
6. `src/mechaharness/model_input_manifest.py` already provides reconstruction and hashing of model-visible messages and tool definitions. `core.types.CompletionRequest` and `ChatMessage` support tools/tool results. Reuse these primitives.
7. Canonical suite is under
   `tests/fixtures/models/static/fixture/v1/suites/fangore_bag_inference_continuity/`.
   Stages `010`/`020` cover M1; `030_fangore_bag_context_spec_continuity` covers M2
   model-input continuity. Inspiration copies under `docs/inspiration/fixtures/`
   are not collected.
8. `src/mechaharness/graph.py` `ExecutionGraph.checkpoint()` dumps the model, and `SqliteCheckpointStore` serializes that checkpoint. An explicitly typed run-bag field on the graph is a plausible minimal persistence path; inspect compatibility and fingerprint implications before selecting it. Avoid changing the entire store API unless necessary.

## Delivery strategy and stop gates

Follow milestones **M0 → M1 → M2 → M3 → M4 → M5** without skipping a gate. Do not implement the full eight-stage coding recipe until `workspace_discovery` works with the real inter-node state contract.

| Milestone | Deliverable | Gate to proceed |
| --- | --- | --- |
| M0 | Existing user stories repaired, collected, and capable of observing real node behavior | Red tests fail for the **intended missing feature**, not schema/collection errors |
| M1 | Typed bag paths, deep snapshots, atomic declared writes, durable checkpoint/resume and subgraph mappings | Bag unit and stepped/restart stories pass |
| M2 | Deterministic ContextSpec compiler, model-input manifests, general inference output publication | A second inference request demonstrably includes authorized state produced by the first |
| M3 | Snapshot-bound read-only inspection tools, transcript records, and separate no-tool judge | Inspection/authorization/snapshot and judge stories pass |
| M4 | Minimum deterministic workspace hard nodes and read-only policy | Hard-node and provenance stories pass |
| M5 | `workspace_discovery` graph and acceptance stories, plus an opt-in live model benchmark | Four discovery outcomes, continuity, safety, checkpoint/replay and offline CI are green |
| M6 (later) | Contract, plan, execution, verification, diagnosis, revision, acceptance composition | Existing `guided_coding` baseline preserved and controlled comparison reproducible |

**Reporting rule:** after each milestone, report changed files, story IDs, commands run with results, observed behavior at the model-input boundary, and remaining risks. Stop and report a blocking incompatibility instead of introducing an unrelated framework.

## M0. Make the acceptance tests real before implementing behavior

**Inspect:** `.cursor/skills/user-stories/SKILL.md`, `tests/stories/scenarios/user_story_scenario.py`, `tests/stories/harness/user_story.py`, `tests/stories/suite_catalog.py`, `src/mechaharness/cli_policy_verbs.py`, `docs/reference/stepped-graph-execution.md`, `tests/stories/test_user_story_suites.py`.

1. Create an authored **parallel** suite at `tests/fixtures/models/static/fixture/v1/suites/fangore_bag_inference_continuity/`. Add `suite.yaml` and individual stages, with distinct story IDs, correct `kind: user_story`, `id/suite/persona/title/narrative/implementation/validation`, `environment`, `graph`, `steps`, `complete`, `cleanup`. Port and strengthen the three previously authored scenarios:
   - `010_bag_continuity.yaml`: `infer_1 → hard_validate → infer_2`; assert exact bag values **and the compiled second model request**.
   - `020_bag_inspection.yaml`: two read-only inspections of the same frozen snapshot, authorization denial, tool budget, and transcript provenance.
   - `030_judge_no_tools.yaml`: fixed judge packet, no tool schema/dispatch, typed verdict or abstention.
2. Do not hand-edit generated `docs/guides/user-stories.md`; run the repository's `sync-suites` and `sync-guide` commands. Update inspiration-document links to the new canonical fixture paths. Remove or explicitly retire old duplicate legacy fixtures only after confirming no remaining references and no lost coverage.
3. Extend the **existing** story-host runner bindings/observations, not the story language, so a graph in a test can use the **actual** injected bag-aware hard/inference/judge runners instead of `GraphWalkVerb`'s universal no-op handler. Preserve existing simple `graph_walk` tests that rely on that handler. Prefer a constrained test-host runner registry/binding rather than a new product CLI verb.
4. Make the useful observations available through existing dotted-path assertions: bag snapshot at pause and after resume; exact compiled requests (or reconstructible model-input manifests); inspection requests/responses; snapshot IDs; node outputs; judge tool-call count. Never expose secrets in normal observability; test fixtures are non-sensitive.
5. Configure static `ScriptedInference`/mock Completer responses as needed, but **capture and assert the actual `CompletionRequest` sent to the fake backend**. A stub that returns correct answers without asserting its inputs is an invalid test of continuity.
6. Verify tests are collected and **red for the expected architectural gap**. Save the red failure evidence in the milestone report. Keep mandatory CI free of permanently failing tests by using an appropriately isolated implementation branch or making the gate green before merging.

**M0 acceptance:** the new suite loads, invokes real code paths, and an intentionally missing `ContextSpec` field or dropped bag write causes an explicit failing assertion. No fake observation flags set to `true` by the story harness.

## M1. Make WalkBag a durable and trustworthy communication channel

**Inspect/change:** `src/mechaharness/walk_bag.py`, `src/mechaharness/graph.py`, `src/mechaharness/graph_executor.py`, checkpoint stores, nested-graph execution paths, `tests/test_walk_bag.py`, graph executor/checkpoint tests.

**Minimal API requirements:**
- Resolve declared register-rooted paths, e.g. `acc.discovery.hypotheses`. Distinguish missing path from present `null`; reject invalid paths and unsupported values. Preserve existing `get/put/require` behavior for current consumers.
- Add a **canonical, bounded, deep** bag snapshot/serialization mechanism for JSON-safe values and explicitly supported typed values (e.g. Pydantic/FileArtifact through tagged schema). Reject unsupported objects with a typed error. Do not rely on `copy.copy` or the current shallow `snapshot()`.
- Add a staged write/commit API for **new bag-aware runners**: validate all declared output paths/types/conflicts before mutating any register. Respect `write_scopes`/concurrency semantics. Do not promise transactional rollback for preexisting arbitrary runner code or external filesystem side effects.
- Persist the bag at every graph checkpoint boundary **together with graph state**. A minimally invasive option is a specifically named typed serialized-bag field on `ExecutionGraph`, hydrated to `GraphRunContext.bag` when resuming. Validate this option against the existing SQLite/EventLog stores, old checkpoints, and config fingerprints before choosing; choose an equally explicit checkpoint-envelope solution if embedding breaks compatibility. Fresh runs need an explicit initial-bag injection mechanism.
- On nested calls, create a **child bag** from declared input bindings; on successful child completion, copy declared outputs into the parent by a validated mapping. No implicit shared object reference or shared mutable nested values.

**M1 unit stories/tests:** nested snapshot remains unchanged after live nested mutation; unsupported serialization fails closed; `out` and `acc` survive pause → reconstruct a **new executor/store instance** → resume; no stale state from a different `run_id`; child modifications only reach parent through mapped outputs; atomic failed validation leaves bag unchanged; unchanged old graph checkpoints remain readable. Test both ephemeral step/resume and SQLite process-restart durability.

## M2. Context compilation and infer-to-bag publication

**Inspect/change:** `src/mechaharness/cli_infer_runner.py` and the appropriate shared inference adapter/runner; `src/mechaharness/model_input_manifest.py`; existing context-pack logic; `core/types.py` request/response models.

Design a versioned `ContextSpec` with:
- declared allowed bag source paths, required vs optional fields, field labels/formatting, output role/message shape;
- stable ordering, deterministic truncation/selection, per-section and global token budgets, evidence provenance, missing-field behavior, and redaction;
- a declared **structured response schema** and final publication destination, distinct from node execution diagnostics.

**Lifecycle per invocation:** freeze the current live bag once → compile `ContextSpec` against snapshot → emit a `ModelInputManifest` of exact messages/tools/omissions and source snapshot ID → call Completer → schema-validate → atomically publish to a declared destination in the **live** bag. Treat node payload as configuration, not implicit shared state. Keep legacy `cli:infer` consumers working where possible; introduce a compatible opt-in bag-aware runner/node kind if unavoidable. A second invocation captures a **new** snapshot with the first invocation's published result; it must not implicitly inherit raw chat history.

**Example conceptual binding, not runnable YAML yet:**

```yaml
id: interpret_evidence
kind: agent_infer
context:
  reads:
    - {path: in.goal, required: true}
    - {path: acc.discovery.hypotheses, required: true}
    - {path: acc.discovery.evidence, required: true}
  token_budget: 2048
response:
  schema: DiscoveryInterpretation
  writes: acc.discovery.interpretation
```

**M2 acceptance:** two real graph inference calls with a hard node between them; the captured I2 `CompletionRequest` includes the goal, I1's structured hypotheses, and validated hard-node evidence, not unrelated bag fields. Assertions compare model-visible content and its manifest with the actual bag/snapshot IDs. An intentionally omitted required field fails before inference. Repeated compilation against the same snapshot/spec yields identical content hashes.

## M3. Snapshot-bound inspection tools and judge isolation

**Inspect/change:** existing tool-loop implementation and DI/configuration, `core.types.ToolDefinition/ToolCall/ToolResult`, `CliInferRunner`, model input manifests, access/budget gates, existing judge runners and stories.

- Implement conceptual `inspect_bag(path, offset, limit)` and `inspect_prior_response(invocation_id, field)` as **read-only inference tools**. Allow only declared paths/response IDs; cap per-call bytes/tokens and total calls. Include structured `denied`, `not_found`, `truncated`, and `unavailable` outcomes. Treat source excerpts and prior model output as untrusted data, never as instructions. Tool results and errors are recorded in the invocation transcript.
- **All** bag tool calls during an inference invocation read the **same immutable invocation snapshot** regardless of subsequent changes to the live bag. Prior response inspection resolves authorized **immutable** transcript records, not arbitrary mutable sibling-node payloads.
- Keep a bounded model/tool loop only for general agent inference. Use existing completion-tool dispatch facilities rather than implementing a second general tool framework. Make tool-call and token budgets explicit. On budget exhaustion or malformed tool calls, return typed terminal failure or bounded escalation, not an infinite loop.
- Provide a dedicated judge contract/runner or strongly isolated mode: same snapshot/context compiler and validation infrastructure but **no tools passed to the judge model, no tool dispatch loop**, typed verdict, evidence references, abstain/insufficient-evidence. Judge failure to produce a valid verdict never becomes an automatic pass.
- Record invocation ID, snapshot ID, manifest, tool request/response pairs, final response/schema errors, and publication target. Reconstruct the same **model-visible context/tool observations** on replay; do not require stochastic models to reproduce identical responses.

**M3 acceptance:** two reads of one nested path see identical values despite an intervening live-bag mutation; forbidden path and prior-response requests are denied and logged; oversized reads truncate within budget; previous authorized response can be inspected; tool observations are traceable to the snapshot and available during replay; judge passes exactly zero tool definitions and makes zero tool calls; judge abstains on missing evidence.

## M4. Deterministic hard-node library for discovery

Use the existing capability contracts in [the architecture document](gastronomic-guided-development.md#deterministic-hard-node-capability-contracts). Every runner declares bag inputs, operation, outputs, permission, validation and failure behavior. Share constrained implementations when appropriate, not one class per noun.

| Priority | Capability | Input | Operation | Output |
| --- | --- | --- | --- | --- |
| P0 | `bag_project` | configured source path + field selectors | validated selective projection | configured `ctx.*` or `acc.*` destination |
| P0 | `bag_validate` | configured bag path + registered schema | validate and return field errors | configured validation report |
| P0 | `workspace_manifest` | `in.workspace`, scope, excludes, read grant | safely enumerate, hash, classify files | `acc.discovery.manifest` |
| P0 | `file_search` | `acc.discovery.hypotheses`, manifest, search limits | bounded literal/regex search with provenance | `acc.discovery.matches` |
| P0 | `source_extract` | file/span refs, manifest/revision | verify source revision; extract exact bounded spans | `acc.discovery.excerpts` |
| P0 | `evidence_resolve` | model-proposed refs, manifest, excerpts | resolve references and reject fabrications | `acc.discovery.verified` and rejects |
| P0 | `coverage_measure` | manifest, queries, matches, exclusions, budget | quantify scanned scope/exclusions/exhaustion | `acc.discovery.coverage` |
| P1 | `bag_merge` | multiple paths + conflict policy | typed union/append/replace | declared `acc.*` destination |
| P1 | `symbol_index` | manifest + language/parser limits | parse supported definitions/imports/usages | `acc.workspace.symbol_index` + gaps |
| P1 | `result_compare` | actual path, acceptance path, comparator spec | schema-aware deterministic difference | `acc.verification.comparison` |

Do **P0 only** before the discovery vertical slice; add P1 if actual user stories demonstrate a need. Avoid adding 10 runners that merely duplicate existing helpers. Every hard-node operation must publish to a **declared bag path**, not an upstream `GraphNode.payload`. Do not put an unrestricted expression interpreter in `bag_transform`.

**Workspace safety:** confine paths to the declared root, defend against symlink/path traversal, report unreadable files, use stable normalized relative paths, record hashes; avoid stale citation acceptance if a file changes after manifest creation. All discovery capabilities are read-only. Record truncation and parser/language gaps. `coverage_measure` is based on observed search coverage, not a model's confidence.

**M4 acceptance:** per-capability unit and story tests for exact input/output paths, required fields, conflict/error behavior, zero partial publication, true source spans/hashes, scan bounds and authorization. Preserve previous bag contents not named in writes.

## M5. Compose and validate the `workspace_discovery` recipe

**New reusable recipe:** `workspace_discovery` (or keep existing `inspect_workspace` alias, but choose and document one canonical name). Implement with existing `GraphTemplate`, runner registry, dependency/tiling machinery, and typed I/O. Discovery must not prepare a code change or mutate workspace files.

**Input:**

```yaml
in:
  goal: "Find the calculator CLI division-by-zero handling and its tests."
  workspace: {root: "<suite-provided workspace>"}
  constraints:
    read_only: true
    max_files: 100
    max_search_results: 50
    max_inference_invocations: 3
    max_inspection_calls: 6
```

**Graph and binding matrix:**

| Node | Kind | Reads from live bag (hard), or call-time snapshot (infer) | Writes to live bag |
| --- | --- | --- | --- |
| H0 `preflight` | hard validate | `in.goal`, `in.workspace`, `in.constraints` | `acc.discovery.preflight` |
| H1 `manifest` | hard `workspace_manifest` | declared workspace/scope | `acc.discovery.manifest` |
| I1 `hypotheses` | inference | snapshot: `in.goal` + bounded manifest summary | `acc.discovery.hypotheses` (search strings, paths/symbol hypotheses, rationale) |
| H2 `search` | hard `file_search` + `source_extract` | manifest + hypotheses | `acc.discovery.matches`, `acc.discovery.excerpts` |
| I2 `interpret` | agent inference | new snapshot: goal + hypotheses + matches/excerpts; optionally `inspect_bag` | `acc.discovery.proposed_findings` (source reference IDs, interpretations, unknowns) |
| H3 `verify` | hard resolve/coverage/validate | manifest + search evidence + proposed findings | `acc.discovery.verified`, `acc.discovery.coverage`, `acc.discovery.validation` |
| H4 `publish` | hard output assembler | verified evidence + coverage + original objective | `out.workspace_inventory` (typed result) |

If coverage is insufficient after one pass, the graph may perform a **bounded** second hypothesis/search/interpretation pass using fresh inference snapshots. Start with one pass; introduce loops only after the one-pass story is proven and a failure trace justifies them. Evidence interpretation is not a tool-enabled permission to edit files.

**Typed `WorkspaceInventory` minimum:**
- `status: found | not_found | inconclusive | failed`;
- `objective`, `workspace_revision` / manifest fingerprint;
- `relevant_files[]` with normalized path, content hash, verified relevant spans, explanation, and traceable evidence IDs;
- `tests[]` with verified paths/spans; `unknowns[]`;
- `coverage` with inspected/eligible file counts, exclusions, search budgets, truncation and reason;
- `rejected_claims[]` or referenced validation diagnostic where useful.

Rules: publish `found` only with verified relevant references; publish `not_found` only after declared adequate coverage; publish `inconclusive` on exhausted/incomplete coverage; publish `failed` for fatal infrastructure/permission/protocol errors. A model cannot set status to `found` by assertion alone.

### Calculator fixture and story matrix

Use a dedicated **read-only calculator discovery workspace fixture** (or safely reuse an existing `calc_cli` stage seed) with `pyproject.toml`, `src/calc/{cli,parser,arithmetic,formatting}.py`, and `tests/test_{cli,parser,arithmetic}.py`. Seed a real division-by-zero check in `arithmetic.py`, CLI propagation/translation behavior, and corresponding real test cases. The gold references must match **actual fixture contents and hashes**. The user gives only the objective and root, **not file paths or solution locations**.

Create an authored parallel suite `fangore_workspace_discovery` with stages:
1. `010_found.yaml`: verified arithmetic/CLI/test references with exact source IDs; no file changes.
2. `020_not_found.yaml`: deliberately absent feature, adequate scan coverage, legitimate `not_found`.
3. `030_inconclusive.yaml`: tiny search/file budget or inaccessible scope, explicit `inconclusive`.
4. `040_failed.yaml`: malformed config, denied read grant or fatal read error, typed `failed`.
5. `050_checkpoint_resume.yaml`: pause after I1/H2; fresh executor + persisted store; resume gives identical bag values and downstream compiled context.
6. `060_inference_continuity.yaml`: I2 request demonstrably includes I1 hypothesis plus H2 evidence; extra unrelated bag field omitted.
7. `070_snapshot_tools.yaml`: I2 permitted inspection, stable snapshot, denied path, transcript manifest.
8. `080_negative_control.yaml`: deliberately remove required prior context in a test-specific configuration; assert **the request-contract validator detects the omission**. In CI the test must pass by checking expected failure; do not add an always-failing test.

Keep judge-specific unit/story tests in `fangore_bag_inference_continuity`; a discovery MVP does not need to invent a judge node when deterministic source verification suffices. Optional semantic judge must be a separate bounded, tool-free step with `abstain`, not a replacement for evidence verification.

**M5 acceptance, offline:** all suite stages pass against static scripted responses; compiled I2 `CompletionRequest` captures prior state; the model can pull permitted snapshot excerpts; the snapshot remains stable; source spans resolve and hashes match; read-only workspace hashes before/after are identical; story checkpoint/resume and subgraph mapping work; failures distinguish `not_found`/`inconclusive`/`failed`; no fabricated references pass validation.

**M5 acceptance, live (opt-in):** run the same behavioral story against configured local Qwen endpoint when available, with bounded invocations/tools/context and full telemetry. Judge endpoint is optional for discovery; where a judge is exercised use configured judge model with no tool calls. A live win requires verified source findings and unchanged workspace, not merely fluent model text. Record actual model ID, settings, tokens, calls, wall time, traces, successes and failure types. Do not fabricate live results if the host or model is unavailable.

## M6. Assemble the complete gastronomic guided coding recipe after discovery

Reuse existing graph templates / coding tool surfaces and defer new primitives unless demanded by user stories. Keep stage state in `acc.stages.*`, reserving `out.development_outcome` for the final published product result. Stage I/O:

| Stage | Consumes | Required behavior / reuse | Publishes | Acceptance gate |
| --- | --- | --- | --- | --- |
| `workspace_discovery` | `in.goal/workspace/constraints` | M5 graph | `acc.stages.discovery` | verified, bounded inventory |
| `contract_extraction` | goal + inventory + tests/known invariants | hard extract/project; infer semantic requirements | `acc.stages.contract` | typed `ChangeContract` with immutable prior invariants and evidence |
| `change_decomposition` | contract + inventory | model proposes small ordered slices; hard schema/dependency checks; optional tool-free judge | `acc.stages.plan` | each slice has scope, checks, rollback, dependency order |
| `change_execution` | one approved slice, file revisions, permissions | reuse coding tools/loop; bounded patch; explicit write grant | `acc.stages.changes` | real diff and changed-file hashes, no scope escape |
| `change_verification` | actual diff + contract checks | reuse `verify_runs`, `verify_repair`, deterministic result comparison | `acc.stages.verification` | host-observed tests; old invariants remain green |
| `failure_diagnosis` | failing command/log evidence + prior attempts | hard log/error grouping + bounded inference explanation | `acc.stages.diagnosis` | evidence-linked failure classification and distinct next experiment |
| `strategy_revision` | diagnosis + plan + retry history | bounded new inference snapshot; deterministic retry/budget gate | `acc.stages.revision` | new evidence/changed strategy or explicit stop/yield |
| `development_acceptance` | contract + verification + diff + coverage | deterministic acceptance gates, optional independent no-tool judge | `out.development_outcome` | `completed | needs_guidance | failed` backed by evidence |

Do not necessarily implement these as eight mandatory graph classes. Extract subrecipes only when independently testable behavior and reuse are established. Constrain repair loops: every retry must add evidence, change strategy, or terminate/escalate. Never mark model assertions as test evidence.

### Final product experiment

Retain original `guided_coding` as baseline. Run the existing six-stage **sequential** `calc_cli` suite with comparable workspace, acceptance checks, tools, model and budgets:
- A: existing guided coding + local Qwen 30B;
- B: gastronomic guided development + same local Qwen 30B;
- C (control): existing guided coding + stronger model; optional D: gastronomic + stronger model.

Record multiple trials, stages passed, prior-regression count, first failure, changed files, calls, prompt/output tokens, tool calls, wall time, repair loops, and guidance yields. Do not claim reliability improvement from a single stochastic run or an unfair inference budget.

## Commands Cursor should run and report

```bash
# Relevant story framework and generated guide:
python -m tests.stories.commands sync-suites
python -m tests.stories.commands sync-guide
python -m tests.stories.commands sync-suites --check
python -m tests.stories.commands sync-guide --check

# First, targeted story suite and bag/executor unit tests:
pytest -q tests/test_walk_bag.py
pytest -q tests/stories/test_user_story_suites.py -k 'fangore_bag_inference_continuity or fangore_workspace_discovery'

# At each stable milestone, run all offline stories and broader tests:
pytest -q tests/stories
pytest -q

# Optional live Qwen integration, only when host has the endpoint:
MECHA_STORY_BACKEND=live \
MECHA_BASE_URL=http://127.0.0.1:8000/v1 \
MECHA_MODEL=qwen3-30b-thinking \
pytest -q tests/stories/test_user_story_suites.py -k fangore_workspace_discovery
```

Follow the repository's actual lint/typecheck/build commands and installed tooling instead of guessing flags. Report skips and unexpected collection counts. A targeted green suite is not a substitute for a full offline regression pass.

## Definition of done for the first deliverable

The **workspace discovery vertical slice** is complete only when:

- [ ] Stories are authored in current suite layout, collected, generated docs synced, and test observations expose real runtime behavior.
- [ ] `WalkBag` values propagate through hard → inference → hard → inference and survive checkpoint/resume including a fresh executor.
- [ ] Nested bag snapshots cannot be mutated through aliases; in-flight inference inspection sees one fixed snapshot.
- [ ] I2's **actual compiled request** contains required I1/H2 state, omits unrelated state, and is replayable via recorded manifests.
- [ ] Permitted and denied inspection tools are bounded, observable, and replayable; judge has no tool loop and can abstain.
- [ ] Hard discovery operations read declared bag paths and publish typed outputs atomically with source hashes/provenance.
- [ ] `WorkspaceInventory` is schema-valid and source-verified for `found`, `not_found`, `inconclusive`, `failed`.
- [ ] No discovery run edits target workspace files; before/after hashes match.
- [ ] All targeted unit/story tests and offline story regression are green; no mocked success booleans.
- [ ] Live benchmark results, if run, are honestly reported with model/config/budgets; otherwise marked **not run**.
- [ ] Inspiration document, story pointers, and PR description are updated with implemented vs outstanding contracts.

**Stop after M5 for review before enabling mutating coding steps.** Document all divergences from this plan and the governing findings. Do not silently broaden scope to a new runtime, new YAML assertion DSL, new universal agent framework, or unrelated recipes.
