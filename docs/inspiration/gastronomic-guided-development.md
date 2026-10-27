# Inspiration: Gastronomic Guided Development (alternative to guided_coding)

**Status:** Architecture and story plan, not implementation
**Reference:** `rl337/mechaharness`, PR #34 (`feat/guided-coding-local-inference`)
**Scope:** One gastronomic product recipe, `gastronomic_guided_development`, and its component subrecipes. The broader guided_usage/reasoning/planning/creativity family is explicitly deferred.

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

### Finding 6: Context projection is an explicit graph boundary
The bag may hold far more evidence than a model can or should see. A hard node should select, rank, compact, and cap a **projection** of that evidence under an explicit context/token budget. Only that projection and the objective enter the soft node. The complete evidence remains in execution state for later inspection, validation, and reuse. Do not confuse the projection with the underlying evidence.

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
Start with hard nodes for workspace enumeration, structural extraction, searching, evidence collection, context projection, validation, and output publication. Add soft nodes only where task interpretation or relevance genuinely requires inference. Preserve full deterministic evidence in the bag, send compact projections to the model, and publish a validated `WorkspaceInventory` in `out`. Include acceptance stories for `found`, `not_found`, `inconclusive`, and checkpoint/resume, and separately test parent/child bag handoff.
