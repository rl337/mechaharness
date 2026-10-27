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
