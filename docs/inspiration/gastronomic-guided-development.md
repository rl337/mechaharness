# Inspiration: Gastronomic Guided Development (alternative to guided_coding)

**Status:** Architecture and story plan, not implementation
**Reference:** `rl337/mechaharness`, PR #34 (`feat/guided-coding-local-inference`)
**Scope:** One gastronomic product recipe, `gastronomic_guided_development`, and its component subrecipes. The broader guided_usage/reasoning/planning/creativity family is explicitly deferred.

**Cursor execution plan:** [gastronomic-guided-development-execution-plan.md](gastronomic-guided-development-execution-plan.md). This is the ordered implementation and verification checklist. It explicitly covers canonical suite-stage migration of the provisional bag test fixtures, actual bag-aware graph-walk execution, durable state propagation, snapshot-bound inspection, and the workspace discovery vertical slice.

## Thesis

MechaHarness's existing agentic recipes evolved bottom-up from concrete requirements. A gastronomic recipe is instead designed top-down from an observable product capability, then decomposed into small reusable recipes that each earn their implementation through practical user stories. This is **not** a new runtime, model-router framework, or universal guided_x interface.

**Product promise:** Given an existing codebase and a bounded development request, a cheaper local model can make a verified incremental change, preserve prior contracts, and either finish or yield an actionable diagnosis to a more capable guide. The system must not confuse more tool-loop attempts with improved problem understanding.

**Experimental question:** Does a deliberately composed development graph improve the same 30B model's reliability relative to PR #34's `guided_coding` under comparable tools, token/call budgets, workspace, and tests? A larger model is a separate control, not the primary success criterion.

## Existing substrate to reuse

The PR #34 catalog already includes `context_pack`, `decision_plane`, `instruction_todo_plan`, `conversational_tool_loop`, `verify_repair`, `independent_review`, `audited_infer_accept`, `bounded_retry`, `fan_out_aggregate`, and `produce_critique_refine`. `guided_coding` currently composes a brief, `instruction_todo_plan`, and `audited_infer_accept`. `ProjectCodingLocalWork` provides workspace tools, `verify_runs`, checkpoints, repair rounds, and escalation guidance.

**Reuse before extraction:** Use existing graph tiling, dependency edges, soft points, durable generator/resume, stop contracts, runner bindings, workspace tools, and deterministic checks. Treat context engineering, evidence-based diagnosis, and invariant capture as candidate missing capabilities, not automatically as new primitives. Keep `guided_coding` unchanged as a baseline.

## Proposed composition

```text
gastronomic_guided_development (product-level recipe)
  intake_and_preflight
    -> inspect_workspace             [candidate subrecipe]
    -> capture_contract              [candidate subrecipe]
    -> design_change                 [candidate subrecipe]
    -> implement_slice               [reuse instruction_todo_plan / tool loop]
    -> verify_change                 [reuse verify_repair + host verify_runs]
    -> diagnose_failure?             [candidate subrecipe]
          -> focused_repair?          [reuse bounded_retry / verify_repair]
          -> revise_change_plan?      [re-enter design_change, bounded]
          -> request_guidance?        [existing soft-point yield/resume]
    -> final_regression_audit         [reuse audited_infer_accept]
    -> outcome
```

These are *responsibilities* first. Do not create one template class per box until a story demonstrates a distinct, reusable graph contract. The product graph can initially tile existing recipes and host leaf operations.

### Product contract

Input: goal, workspace reference, acceptance criteria, optional guidance, model/tool bindings, budget, and prior checkpoint. Output: `completed | needs_guidance | failed`, verified artifacts, evidence references, changed files, preserved invariants, remaining failures, and suggested next action. Distinguish model assertions from host-observed test results.

### Intermediate artifacts

1. **WorkspaceInventory**: entry points, relevant files, tests, interfaces, known unknowns, evidence paths and hashes.
2. **ChangeContract**: requested behavior, invariants, prohibited changes, verification commands, assumptions and provenance.
3. **ChangePlan**: small independently testable slices, dependency order, intended file boundaries, rollback points.
4. **VerificationReport**: actual command results, failing assertions, regression status, tool/protocol errors, artifact versions.
5. **Diagnosis**: failure class, evidence, suspected cause, next experiment, confidence, prior attempted repairs.
6. **DevelopmentOutcome**: acceptance evidence and references to the preceding artifacts.

Prefer lightweight typed payloads or existing persisted graph state, not an additional database. Artifacts must be inspectable and resumable; each downstream step receives a *focused projection*, not an unbounded transcript.

## Candidate component subrecipes and practical stories

| Order | Responsibility | Existing leverage | First practical user story | Acceptance |
|---|---|---|---|---|
| 0 | Baseline instrumentation | existing timing spans, suite runner | As an experimenter, I can replay `calc_cli` and see the first failure by category | Trace records stage, model, tokens/calls, tool errors, verification, checkpoint and outcome |
| 1 | `inspect_workspace` | context_pack, workspace read tools | As a coding agent, I can inspect an existing calculator before modifying it | Inventory names real files, current API, CLI, tests, and supporting evidence; no writes |
| 2 | `capture_contract` | acceptance policies, audited criteria freeze | As a maintainer, I can preserve already-working number/add/sub behavior while adding multiplication | Explicit prior invariants and executable checks are frozen before editing |
| 3 | `design_change` | instruction_todo_plan, decision_plane | As a coding agent, I can propose a bounded parser extension without rewriting unrelated grammar | Plan identifies change boundary, order, risks, and test for each slice |
| 4 | `implement_slice` | conversational_tool_loop, coding tools | As a coding agent, I can apply exactly one planned change | Real file write, tool result, and changed-file evidence; respects budget |
| 5 | `verify_change` | verify_repair, verify_runs, audited_infer_accept | As a maintainer, I can prove new functionality and all previous regression cases still work | Host executes checks; false model claims cannot pass |
| 6 | `diagnose_failure` | independent_review, decision_plane | As an agent, I can distinguish syntax, tool protocol, runtime, semantics, regression, and budget failures | Diagnostic classification links to actual failing evidence and recommends a distinct next action |
| 7 | `replan_from_evidence` | bounded_retry, guidance yield, checkpoint restore | As an agent, I can stop repeating an ineffective fix and revise strategy or ask for guidance | Repeated identical failure cannot cause unbounded retries; previous failed hypotheses recorded |
| 8 | `final_regression_audit` | audited_infer_accept | As a maintainer, I receive a defensible acceptance verdict | Every required check has evidence; incomplete coverage cannot be reported as success |

Candidate names are provisional. For each story, first test whether an existing recipe plus a runner binding suffices. Extract a new subrecipe only when its independent contract and reuse are demonstrated.

## Calculator suite as the initial product benchmark

Use PR #34's sequential `calc_cli` stages unchanged: number, add/sub, multiply/divide, exponentiation, grouping, functions. The same workspace accumulates changes; earlier checks must stay green. Preserve `evaluate(expr)`, `main(argv=None)`, CLI exit codes, and the no-`eval`/`exec`/`ast.literal_eval` restrictions. The existing live Completer is the acceptance gate; static fixture success is only provisional.

Run **A**: existing `guided_coding` with Qwen 30B. Run **B**: gastronomic guided development with the same Qwen 30B, tools, suite, and controlled budgets. Run **C**: original graph with Nemotron Super to measure model capability separately. Optionally run **D**: gastronomic graph with Nemotron. Use multiple trials with recorded settings; avoid declaring a winner from one stochastic run.

Report: stages passed, prior regressions, first failure type, verified successful edits, model calls, input/output tokens, wall time, guidance calls, repair cycles, and repeat-failure loops. Record both aggregate and per-stage results. Do not compare only completion rate if one graph uses far more inference.

## Implementation increments and stop/go gates

**Increment 0: Observability and baseline.** Capture the existing PR #34 live failures. Identify whether failures are tool-format, execution, reasoning, context, or validator failures. No new recipe yet.

**Increment 1: Inspect + contract.** Implement the smallest inspect-and-freeze composition; demonstrate a stable, cited inventory and preserved API/invariants on calculator stages 1–3. Verify it works when resumed from a checkpoint.

**Increment 2: Bounded change.** Add plan/implement/verify composition using existing tool loop and verify machinery. Compare to the baseline on stages 1–4.

**Increment 3: Evidence-driven recovery.** Introduce diagnosis only if traces show undifferentiated repair loops. Test one induced precedence bug, one malformed tool-call response, and one stale-workspace regression. Require different remediation outcomes.

**Increment 4: End-to-end alternative recipe.** Run all six stages live, preserve prior checks, and produce a machine-readable outcome. Repeat trials and compare budgets.

**Increment 5: Generalization.** Apply one extracted subrecipe to `counter_pkg` or `delegate_pkg` before stabilizing its public catalog contract. Avoid calculator-specific names or assumptions in reusable code.

## Engineering guardrails

- Do not modify `guided_coding` merely to make the new approach pass; retain a fair baseline.
- Do not introduce `guided_usage` or other guided expert recipes in this effort.
- No global universal `guided_x` schema; only the development product's minimum contract.
- Reuse `GraphTemplate.tile`, soft points, dependency injection, existing checkpoint and generator machinery.
- Do not invent success based on a model-written summary; deterministic host evidence is authoritative for executable checks.
- Context packets must be bounded, source-linked, version-aware, and purpose-specific. Summaries cannot silently override source code.
- Separate implementation errors from malformed tool protocol and infrastructure errors.
- Every retry must either add evidence, change strategy, or terminate/escalate.
- Keep static deterministic stories for subrecipe contracts and at least one real-model integration gate.
- Prefer small, reviewable implementation PRs for individual subrecipes and user stories.

## Open design questions

1. Should `WorkspaceInventory` and `ChangeContract` be existing graph-state payloads, files in the workspace, or both?
2. Which existing `context_pack` capabilities already satisfy focused context selection?
3. Does the current host tool-loop support native tool calling for the local model, or must prompt-tool serialization be separately benchmarked?
4. What is the smallest cross-recipe artifact contract needed for durable resume and independent verification?
5. Which first failure in the current live `calc_cli` trace is actually causal? Do not prioritize speculative abstractions over observed failures.

## Definition of done for this inspiration phase

A reviewed composition design, ordered subrecipe/story backlog, baseline experiment protocol, and clear first implementation slice. No claim that the gastronomic recipe improves Qwen reliability until a live controlled comparison supports it.

## WalkBag state and debugger checkpoint contract

The existing `WalkBag` is the native node-to-node state carrier within a running graph. Node runners access the mutable bag through `GraphRunContext.bag`; gastronomic recipes must use that mechanism rather than introducing a parallel artifact store or writing Markdown files. The register ABI (`in`, `out`, `acc`, `ctx`, `ask`, `ans`, `err`) is the starting point; any richer schema is a value stored in a register, not a new test verb.

**Required user-story behavior:** whenever the YAML story executor checkpoints a paused graph walk, it must serialize the current bag contents alongside the graph execution state. Resuming from that checkpoint must reconstruct the bag before any subsequent node executes. A debugger inspection immediately before a node or before entering a subgraph must therefore see the same bag values that the node will consume. This is a test-framework execution contract, not a new semantic recipe or YAML verb.

**Separate boundary concern:** a nested graph currently creates its own run context and bag. Do not assume the child's `out` automatically appears in the parent's bag. Define and test explicit input/output mapping at subgraph boundaries before relying on nested gastronomic composition. This is distinct from checkpoint persistence.

Acceptance stories should prove: (1) a node writes a structured value into `out` or `acc`; (2) the story pauses before the next node and inspects it; (3) a checkpoint is serialized and the executor is reconstructed; (4) the resumed node reads the exact value; (5) the child graph receives declared inputs and publishes declared outputs through an explicit boundary mapping. Include nested checkpoint/resume and reject or explicitly encode non-serializable bag values rather than silently dropping them. Use the existing `graph_walk` and story assertions; do not add debugger-specific verbs.

**Implementation status:** requirement/design only. Current `WalkBag.snapshot()` is shallow, and inspected `GraphExecutor` paths construct a new `GraphRunContext` on resume. Confirm the full story checkpoint machinery before choosing the serialization hook; do not mark this behavior implemented without a passing story.

## Findings of fact and governing design principles

The following findings record architectural conclusions established during recipe design. Treat them as durable precedents: future recipes should conform to them unless a subsequent explicit design decision supersedes a finding. These are design rulings, not claims that all required behavior is already implemented.

### Finding 1: The bag is the native execution-state carrier
MechaHarness provides a mutable `WalkBag` through `GraphRunContext.bag`. Nodes within a run communicate through its register ABI (`in`, `out`, `acc`, `ctx`, `ask`, `ans`, `err`). A recipe's machine-inspectable result should be published through this mechanism. A Markdown file or separate artifact store is not required merely to make recipe outputs testable.

### Finding 2: Runtime availability and checkpoint durability are distinct
The bag is available to nodes during live execution. The YAML user-story debugger must also serialize bag state with checkpoints and restore it before the next node runs. This is a requirement to implement and verify, not an assumption about the current executor. The current `WalkBag.snapshot()` is shallow, so checkpoint serialization needs an explicit value/encoding contract.

### Finding 3: Subgraph state is not implicitly shared
Nested graph execution constructs a distinct run context. Parent/child recipes need explicit, testable input and output transfer across that boundary. Sharing the budget ledger does not imply sharing the bag.

### Finding 4: Hard nodes and inference tool calls have different context economics
A deterministic **hard node** executes as part of the graph outside any inference call's context window. It may scan a repository, parse ASTs, build indexes, follow references, compute coverage, and update the bag without placing its intermediate data into model context. A deterministic **tool call made by a soft/inference node** still participates in an inference interaction: its invocation and returned observations can consume context. These mechanisms must not be treated as interchangeable simply because both ultimately run deterministic code.

### Finding 5: Prefer deterministic execution over model orchestration
Every operation that can be expressed as reliable deterministic code should be a hard node, especially filesystem enumeration, search, syntax/AST extraction, reference validation, set membership, budget accounting, and schema checks. Soft nodes are reserved for irreducible semantic tasks such as proposing search hypotheses or judging relevance. A soft node should not be asked to infer facts that deterministic code can establish.

### Finding 6: Context projection is an explicit execution boundary
The bag may hold far more evidence than a model can or should see. Deterministic context compilation within an inference node selects, ranks, formats, and caps a **projection** of immutable call-time state under an explicit token budget. It need not be a separate graph node. Only that projection and declared instructions enter the initial model call; bounded read-only inspection tools may supply additional projections from the same snapshot. Do not confuse any projection with the underlying evidence.

### Finding 7: Inference produces hypotheses and bounded judgments, not source facts
A model may propose search terms, candidate relationships, or relevance assessments. Deterministic nodes execute searches and check cited files, symbols, and source spans. Published claims should be traceable to verified evidence; model-produced statements without supporting evidence remain hypotheses or unknowns.

### Finding 8: Discovery is objective-directed and may legitimately find nothing
`workspace_discovery` receives a caller-supplied natural-language objective and workspace (with optional scope and budget). Its purpose is to identify workspace evidence relevant to that objective, not to exhaustively index everything or create a change plan. Distinguish `found`, `not_found`, `inconclusive`, and `failed`. A well-supported negative discovery is a valid result, while exhausted or inadequate coverage is inconclusive. Do not pressure the model to manufacture relevance.

### Finding 9: Working state and published output have different contracts
Intermediate indexes, search histories, candidate sets, and evidence can remain in the bag as working state. The final `WorkspaceInventory` is a schema-validated, bounded, machine-inspectable result published to `out`. The inventory should contain relevant findings, provenance, search coverage, and unknowns, without duplicating the entire index or prematurely prescribing code changes.

### Finding 10: Recipe decomposition follows independent, testable semantics
A recipe is a bounded, composable unit with meaningful inputs, outputs, and acceptance criteria; a simple `read_file` or `search_text` operation is ordinarily a tool/hard-node operation, not automatically a separate recipe. `workspace_discovery` may orchestrate deterministic analysis and a small number of inference decisions. Prefer the smallest number of soft nodes that reliably performs the semantic work, and do not over-decompose into inference-heavy wrappers.

### Finding 11: Existing user-story and graph-walk facilities are the acceptance surface
Use the existing YAML user-story framework and `graph_walk` stepping, including before/after pauses, subgraph entry, checkpoint, and resume. Do not invent new YAML verbs or a parallel testing infrastructure. Test hard-node outputs exactly, test soft-node decisions against controlled evidence, and verify that a checkpointed bag is restored intact. Distinguish test requirements from passing implementation.

### Finding 12: Discovery does not imply authorization to modify the workspace
Discovery should use read-only workspace operations and should not mutate target source files. Its product feeds subsequent contract extraction and planning recipes; those stages, not discovery, determine what changes should be made.

### Consequences for the first workspace-discovery implementation
Start with hard nodes for workspace enumeration, structural extraction, searching, evidence collection, validation, and output publication. Context compilation is deterministic but belongs inside the inference-node lifecycle rather than requiring a separate graph node. Add soft nodes only where task interpretation or relevance genuinely requires inference. Preserve full deterministic evidence in the bag, send compact projections to the model, and publish a validated `WorkspaceInventory` in `out`. Include acceptance stories for `found`, `not_found`, `inconclusive`, and checkpoint/resume, and separately test parent/child bag handoff.

### Finding 13: Inference sees an immutable, call-time bag snapshot
At the start of each inference invocation, capture an immutable snapshot of the live `WalkBag`. The inference node's deterministic context compiler builds the initial prompt from that snapshot, not from mutable live state. Read-only inspection tools invoked during the same inference interaction may retrieve bounded projections of **that same snapshot**, never the subsequently mutated live bag. Prior inference responses may be inspected through separately scoped, immutable execution records. The inference transcript must identify the snapshot/version it observed and record inspection requests and returned projections for audit and replay. Snapshot immutability must be deep or serialization-based: the current shallow `WalkBag.snapshot()` does not by itself guarantee isolation of nested values. Deterministic replay promises identical compiled context and inspection observations for the same snapshot/spec/tool inputs, not identical stochastic model responses. This is a design requirement, not yet verified implementation.

### Finding 14: Context compilation belongs to the inference node lifecycle
The inference node owns deterministic bag-to-context compilation immediately before invoking its model. This does not require an additional graph node. A reusable context compiler accepts a declared `ContextSpec`, immutable bag snapshot, and token budget to produce an inspectable `CompiledContext` with provenance and omission metadata. The inference engine receives only that bounded projection. During the inference interaction, authorized read-only tools may retrieve further bounded projections of the frozen snapshot or prior response records; these are explicit, observable context additions, not access to mutable live state.

## Inter-node communication and inference-state contracts

This section formalizes how graph nodes exchange state, and how model-backed nodes consume that state. It is the normative design direction for this inspiration document; existing code must be checked against these contracts before claiming implementation.

### State and ownership boundaries

- **Live WalkBag:** the graph run's mutable register-based communication state. Hard nodes read/write it as permitted by their node contracts. The `in/out/acc/ctx/ask/ans/err` registers remain the existing ABI; structured values within them have typed schemas where useful.
- **Node contract:** declares required input registers/paths, produced outputs, permitted mutations, and error behavior. A node must not assume unrelated register values are present or valid.
- **Inference snapshot:** a deep-immutable, point-in-time capture of the bag when an inference invocation begins. The model-backed node and its tools read this version for the duration of that invocation.
- **ContextSpec:** a declarative, versioned policy defining the bag paths, formatting, ranking/selection, budget, provenance, and omission behavior for initial model context. It is not a license to serialize the entire bag.
- **CompiledContext:** the exact messages/structured input sent to the model, with a manifest of source paths, versions, omissions, and budget accounting. Compiled context is derived deterministically from the snapshot and ContextSpec.
- **Inference transcript:** immutable execution record of compiled input, model responses, inspection requests and results, and final output. Its records are distinct from the values a node elects to publish into the live bag.
- **Published result:** schema-validated node output written back to declared bag destinations after inference finishes; it must not retroactively change the snapshot used by that inference.

### Node kinds have different communication semantics

| Node kind | Reads | Computation | Tool calling | Writes |
| --- | --- | --- | --- | --- |
| Hard/deterministic | Declared live bag state at node execution | Ordinary code, outside model context | Host/library operations as code, not inference-loop tools | Declared bag outputs |
| General inference/agent | Immutable invocation snapshot, initially via compiled context | One or more model turns | **May** call explicitly authorized tools to inspect bounded views of the *same* snapshot and prior immutable response records; other tools require separate explicit capabilities | Validated final outputs to live bag |
| Judge | Immutable invocation snapshot, via a compiled judging context | Bounded evaluation/classification/scoring model call | **No model-initiated tool calling in the default judge contract** | Typed judgment, confidence/evidence references, and diagnostics to declared bag outputs |

A judge is a **specialized model-backed node**, not an agent node with an empty tool list by accident. Its API should intentionally express no tool loop, a fixed evidence envelope, a typed verdict schema, and explicit abstention/uncertainty behavior. If a judge needs more evidence, the enclosing graph gathers it with hard nodes or a separate agent and invokes the judge again with a new snapshot. This keeps judging repeatable and prevents the judge from changing its own evidence set mid-evaluation. Whether some future judge variant supports tools is a separate design decision, not a property to assume now.

### General inference node lifecycle

1. Capture/freeze the current bag at invocation start; assign a snapshot identity and record source/provenance.
2. Resolve the node's ContextSpec against **that snapshot** using a reusable deterministic context compiler running inside the inference-node runner. Validate access, schemas, and budget; record the compiled input.
3. Invoke the selected model with the compiled input and the node's declared output contract.
4. If the node is a general inference/agent node and tools are enabled, handle authorized inspection requests against the same frozen snapshot. Each response is size-bounded, logged, and included in the model transcript. Prior response inspection must identify which previous response/record is visible; do not silently expose arbitrary history.
5. Validate the final model response against the declared schema, including evidence references and uncertainty; publish only permitted outputs into the **live** bag and persist the transcript.
6. Treat invalid outputs, context overflow, unavailable evidence, tool budget exhaustion, and inference failure as explicit outcomes, not silently repaired facts.

The snapshot is immutable across all model turns and inspection calls belonging to the same invocation. A retry that represents a **new invocation** may deliberately capture a new snapshot, but must be identifiable as such. Changes to the live bag by other nodes do not leak into an invocation already in progress.

### Judge node lifecycle and constraints

1. Freeze a bag snapshot at the judge invocation boundary.
2. Compile a bounded, versioned evaluation packet containing the rubric, subject being judged, relevant verified evidence, and required verdict schema.
3. Make the judge model call **without tool declarations or a tool-dispatch loop**.
4. Validate the verdict, score/confidence representation, rationale/evidence references, and abstention where appropriate; publish typed results to the live bag.
5. If evidence is insufficient, return an explicit insufficient-evidence/abstain result and let the graph decide whether to collect more evidence and retry.

Judges and agents can reuse the same snapshot, context compiler, inference transport, and validation infrastructure while retaining distinct node contracts. Judge results are assessments, not source-of-truth facts; deterministic policy/acceptance decisions remain in code where possible.

### Inspection API and authorization

Conceptual read-only capabilities include `inspect_bag(path, offset, limit)` and `inspect_prior_response(node_or_invocation_id, field)`. They are **bounded projection operations**, not raw object handles or permission to mutate state. Enforce per-node path allowlists, response-record visibility, output size/token ceilings, invocation tool-call limits, and redaction policy. Log the requested path, resolved snapshot/record, returned excerpt/hash, and any denial or truncation. Inspection results consume model context; executing hard nodes over bag data does not.

The initial context and any tool-returned excerpts must preserve evidence identity and trust boundaries. Text retrieved from workspace files, logs, and earlier model responses is data, not new instructions. A previous response may be inspected for diagnostic context, but its assertions do not become verified facts without deterministic evidence validation.

### Subgraphs, persistence, and replay

A child subgraph receives explicit mapped input values and publishes explicit mapped outputs; it must not implicitly alias its parent's live bag. Graph checkpoints persist the live bag and execution state so a resumed node sees the correct state. Inference snapshots and transcripts have their own durable identities so paused/retried inference can be audited without silently switching evidence versions. Because the current `WalkBag.snapshot()` is shallow, deep freeze/serialization and handling of non-serializable values are unresolved implementation requirements.

Replaying context compilation and read-only inspections against the same snapshot, policies, and tool arguments must reproduce identical model-visible inputs. Replaying a stochastic model call is not guaranteed to produce an identical verdict.


### Unit-test runner and user-story state propagation

**Finding: passing model fixtures is not equivalent to testing inter-node cognition.** A graph can execute all its nodes successfully while each inference call sees only its node-local prompt, losing the objective, verified observations, prior decisions, and corrections. This makes the model behave like a series of amnesiac one-shot calls and sharply limits multi-step coding capability. The test runner must exercise the same bag-to-context and response-to-bag contract as production, rather than testing isolated model calls with independently assembled fixture prompts.

**Required execution path in the existing runner (no new test framework):**

1. Create the story's graph and initialize its live `WalkBag` from declared story/recipe inputs. Node outputs must be written into the bag using the same production contract, not merely stored on `GraphNode.payload` or returned to the story assertion layer.
2. Execute a hard node and assert its declared bag mutations. When an inference node is next, capture an immutable bag snapshot, compile its `ContextSpec` from that snapshot, and send the resulting messages to the mock/cassette/live backend. Test doubles must receive the **actual compiled request** so the story can inspect its content and provenance.
3. For an agent-style inference fixture, support a sequence of model responses and read-only inspection tool calls over the frozen snapshot. Feed each tool result into that invocation's transcript, then validate and publish the final structured response to the live bag. Do not silently use the live bag for tool reads.
4. Execute the following inference node against a **new snapshot of the updated live bag**. The node's ContextSpec must explicitly select prior structured outputs, evidence, and/or transcript excerpts needed for its task. **Preserve state across inference calls, not the entire raw chat history by default.** Each call is fresh in model context but not amnesiac in task state.
5. Judge-node fixtures use the same snapshot and compilation path but one model response and no tool dispatch. A judge's typed verdict must become accessible to downstream nodes through declared bag outputs.
6. At every existing `graph_walk` checkpoint, serialize live bag state with the graph; restore it before the next node executes. Verify nested values, explicit parent/child mappings, and replay of compiled context and inspection responses. Persist immutable invocation snapshot/transcript identities where a paused inference must be inspected or replayed.

**Concrete regression story: multi-inference continuity.** In a small calculator workspace, the first inference node identifies relevant files and hypotheses and publishes a structured discovery result to `out` or another declared register. A hard node validates source references and writes verified evidence. The second inference node proposes a bounded change using the objective, the verified evidence, and the first inference result selected by its ContextSpec. A judge then evaluates the proposal using its own compiled evidence packet, without tools. Assert that the second model request actually includes the required prior facts, that unrelated bag contents are omitted, and that the judge sees the proposal and evidence. Pause/checkpoint between calls, resume, and assert the same model-visible inputs. Include a negative control where prior state is deliberately omitted and the fixture or request-contract assertion fails.

**Implementation review targets:** `GraphRunContext.bag` in `graph_executor.py`; `cli_infer_runner.py` (currently a one-shot inference runner); `context_pack_runner.py` (currently reads upstream node payloads); the existing static-fixture/cassette user-story runner; and `graph_walk` checkpoint/resume. Review these paths to locate where state is dropped, rather than assuming the absence of continuity is already proven for every runner. The existing `model_input_manifest` and context-related user stories may provide reusable request-recording and assertion mechanisms.

**Acceptance criterion:** a sequence of two inference calls separated by hard nodes must demonstrate that information written by the first call survives in the bag and is deliberately projected into the second call's request. Merely asserting that both inference calls returned successful responses is insufficient. The implementation must prove state continuity *at the model-input boundary*.

**Status:** design and required tests; not implemented or verified by this documentation change.

### Tracked user-story fixtures (initial red specifications)

The following checked-in fixtures are the concrete acceptance-test backlog for this communication contract. **Keep this pointer current when moving, implementing, or replacing them** so the tests do not become detached from the architectural ruling:

- [Story manifest](../../tests/fixtures/models/static/fixture/v1/stories/fangore_bag_inference_continuity/story.json) defines the `fangore_bag_inference_continuity` story.
- [`bag_continuity.yaml`](../../tests/fixtures/models/static/fixture/v1/stories/fangore_bag_inference_continuity/scenarios/bag_continuity.yaml) covers state propagation from discovery through validation into a subsequent inference request.
- [`bag_inspection.yaml`](../../tests/fixtures/models/static/fixture/v1/stories/fangore_bag_inference_continuity/scenarios/bag_inspection.yaml) covers immutable bag snapshot inspection, authorization, and transcript recording.
- [`judge_no_tools.yaml`](../../tests/fixtures/models/static/fixture/v1/stories/fangore_bag_inference_continuity/scenarios/judge_no_tools.yaml) covers compiled judge evidence, typed verdicts, and the absence of tool calls.

These are **red test specifications**, not proven passing tests. The existing runner must be wired to support their fixture behavior and observations before they can establish correctness. Do not mistake their presence in the repository for successful validation.

### Acceptance stories to add using existing YAML graph-walk machinery

- Hard node publishes nested structured bag state; a later hard node consumes the exact value; checkpoint/resume preserves it.
- General inference node receives only its declared context projection, not unrelated bag fields; truncation and omitted-evidence manifests are inspectable.
- A model calls `inspect_bag` twice during one invocation; both reads observe the same deeply frozen snapshot even if live state subsequently changes.
- A model inspects a permitted prior response, and an unauthorized path/record request is denied and logged.
- An inference result publishes a validated typed value to the live bag without mutating its input snapshot.
- A judge receives the same snapshot/projection substrate but has **no tool-calling interface**; it returns a typed verdict or abstention. Insufficient evidence triggers graph-level follow-up, not an internal judge tool loop.
- Child recipe mapping and checkpoint/resume preserve declared values without implicitly sharing parent/child bag objects.
- Context compilation, inspection, and transcript replay reproduce identical model-visible evidence for the same snapshot, independent of model-output nondeterminism.

**Open design choices:** exact ContextSpec schema; immutable snapshot representation and retention; how concurrent writes are ordered at capture; output merge/conflict policy; transcript persistence and response visibility; judge verdict schema and confidence calibration; precise handling of retries and paused in-flight calls. Do not present these as settled or implemented.

## Deterministic hard-node capability contracts

The following is a proposed implementation specification for a reusable hard-node capability library. It formalizes the inputs, computation, outputs, and failure behavior of each operation. **These are design contracts, not assertions that these runner kinds or YAML fields already exist.** Audit existing MechaHarness runners and helpers before adding new implementations.

### Shared configuration and execution contract

A hard-node configuration declares: (1) input bag paths and required schemas, (2) operation parameters, (3) output bag paths and schemas, (4) permitted side effects/capabilities, and (5) error and conflict policy. Inputs and outputs must not be inferred from incidental node payloads or arbitrary global state.

Illustrative *proposed* configuration, not current YAML grammar:

```yaml
id: project_discovery
kind: bag_transform
operation: project
reads:
  source: acc.workspace_inventory
parameters:
  fields: [relevant_files, verified_symbols, unknowns]
writes:
  destination: ctx.discovery_summary
  mode: replace
on_error:
  destination: err.project_discovery
  policy: fail
```

Execution sequence: resolve declared bag paths → validate schemas and permissions → perform deterministic operation → validate outputs → atomically commit declared writes → record structured execution diagnostics. A failure must not leave partially published bag mutations. For pure transforms, identical input/configuration produces identical output. For workspace operations, reproducibility also requires recording the observed workspace revision, file hashes, relevant environment, and external command versions where applicable. Any explicit filesystem mutation requires a separate authorization and rollback/partial-effect contract; bag atomicity alone cannot roll back external side effects.

Use the existing `WalkBag` registers (`in`, `out`, `acc`, `ctx`, `ask`, `ans`, `err`) with structured values stored beneath them. Working data ordinarily lives under `acc`/`ctx`; published recipe results under `out`; diagnostics under `err` or an explicitly declared diagnostic path. These are conventions, not an implicit data-routing mechanism: the node's declared write destinations govern.

### Initial capability registry

| Capability | Declared inputs | Deterministic computation | Declared outputs | Failure / boundary semantics |
| --- | --- | --- | --- | --- |
| `bag_project` | Source structured value, e.g. `acc.workspace_inventory`; selected field paths and optional rename/default policy | Select/rename nested fields into a new object; do not mutate source | `ctx.discovery_summary` | Missing required path or schema mismatch is typed failure; optional defaults explicit |
| `bag_merge` | Multiple paths, e.g. `acc.search_results`, `acc.symbol_results`; merge policy | Merge via declared replace/append/keyed-union/reject-conflicts strategy | `acc.evidence` | Conflicts rejected or resolved only by declared policy; no silent overwrite |
| `bag_validate` | Value e.g. `out.discovery`; versioned schema/registered contract | Check schema and produce field-level diagnostics | `acc.validation.discovery` | Invalid value yields structured report; optional fail-node policy |
| `workspace_manifest` | `in.workspace` root/scope; ignore rules; traversal limits; filesystem-read grant | Enumerate normalized relative paths; classify types; collect size/hash; record exclusions | `acc.workspace.manifest` with files, omissions, errors, coverage | Inaccessible paths, symlink escape, traversal limits, and races reported explicitly |
| `file_search` | `ask.search_queries`; `acc.workspace.manifest`; `ctx.search_budget` | Literal/regex search within declared scope; deduplicate; capture paths, line ranges, hashes | `acc.search.matches` with provenance/truncation | Invalid patterns, changed files, and budget exhaustion reported; no fabricated matches |
| `source_extract` | `ask.source_requests` file/span refs; manifest/revision | Check path and revision; read bounded exact lines/syntax spans | `acc.evidence.excerpts` with text, location, hashes, rejected requests | Stale refs, missing files, out-of-bounds spans, size limits explicit |
| `symbol_index` | Manifest file set; language/parser configuration; limits | Parse supported source files; extract definitions/imports/exports and stable symbol locations | `acc.workspace.symbol_index` plus diagnostics/coverage | Unsupported language and parse failures become coverage gaps, not invented symbols |
| `evidence_resolve` | Model-proposed claims/refs e.g. `out.discovery`; manifest and verified excerpts | Resolve cited file/symbol/span identities, revision, existence, and support references | `acc.evidence.resolution` with verified/rejected/unresolved entries | Reference verification is deterministic; semantic truth beyond deterministic checks remains unverified |
| `coverage_measure` | Search history, scoped manifest, parser coverage, budgets/thresholds | Calculate searched scope, exclusions, exhaustion, threshold satisfaction | `acc.discovery.coverage` with metrics, omissions, threshold results | Insufficient coverage must not be relabeled `not_found`; distinguish inconclusive |
| `result_compare` | Actual e.g. `out`; expected `in.acceptance`; comparator config | Schema-aware exact/set/tolerance comparisons with explicitly ignored volatile fields | `acc.verification.comparison` with pass/fail and mismatch paths | Unsupported comparison types, invalid expectations, and schema mismatch reported |

These example paths demonstrate data flow; actual recipes may bind other declared paths without changing capability semantics.

### Capability granularity and reuse

A capability is a deterministic operation, **not necessarily a separate Python runner class or agentic recipe**. Closely related bag transformations may share a constrained `bag_transform` runner with registered operations. Avoid an unrestricted expression/scripting language: each operation needs a stable schema, permissions, explicit writes, and predictable failure semantics. An agentic recipe composes hard capabilities and inference/judge nodes into an independently testable objective.

Keep the context boundary from the preceding section: hard nodes may prepare, rank, and validate evidence in the live bag, but the inference node itself compiles its declared context from an immutable call-time snapshot. Hard nodes must not implicitly inject the whole bag into a model request.

### User-story acceptance matrix

For **each** capability, add an existing-framework YAML user story that initializes declared bag inputs, steps the hard node, inspects its exact output path, checks unrelated state remains unchanged, checkpoints and resumes before a downstream consumer, and verifies failure/denial behavior. Add property-style cases where useful (merge conflicts, invalid regex, stale source hashes, symlink escapes, missing fields, unsupported parsers, and coverage exhaustion). Test input/output schema errors and partial-write prevention. These are **required future tests**, not yet authored or run by this section.

The existing inference-continuity fixtures linked above are the cross-node integration acceptance surface: verify that hard-node evidence and prior inference outputs survive in the bag and appear only through a subsequent inference node's declared context projection.

**Open design choices:** exact runner/YAML binding syntax, whether path resolution is a common runtime service, merge/version conflict handling, external effect idempotency, schema registry/versioning, and how to represent workspace revisions. Decide these with reference to the current code and existing story machinery before implementation.
