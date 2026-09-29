# Developer Blog Inspiration for MechaHarness / June

> Living design-notes document. External developer material is evidence and inspiration, not specification. Requirements below generalize ideas only where they strengthen MechaHarness and June.

Last reviewed: 2026-09-29

## Purpose

This document tracks useful agent-harness ideas from Claude/Anthropic and Cursor and translates them into testable MechaHarness requirements. It is deliberately provenance-heavy: every inspiration-derived requirement names the source material that motivated it. The goal is not product compatibility. It is to challenge MechaHarness assumptions against production agent systems and retain only patterns that generalize.

## Requirements

### 1. Harness scaffolding must be revisable and retirable

**Sources**
- Claude, **Agent Harness Design: 3 Patterns for Harnessing Claude's Intelligence** (2026-04-02): https://claude.com/blog/harnessing-claudes-intelligence
- Cursor, **Continually improving our agent harness** (2026-04-30): https://cursor.com/blog/continually-improving-agent-harness
- Cursor, **Improved token efficiency for longer agent runs** (2026-09-23): https://cursor.com/blog/improved-token-efficiency

**Requirements**
- Orchestration policy SHOULD be replaceable configuration rather than permanent intelligence embedded in framework code.
- Every nontrivial intervention SHOULD identify the failure mode it addresses and evidence for its existence.
- Harness experiments SHOULD compare execution with and without an intervention.
- Model/runtime upgrades SHOULD trigger retirement tests for existing scaffolding.
- Policies that no longer improve outcomes SHOULD be removable without changing task semantics.
- Token, latency, compute, memory and coordination overhead SHOULD count against retaining scaffolding.

For June, stronger local models should be allowed to absorb work previously supplied by explicit scaffolding rather than leaving a fossil layer of obsolete prompts and control logic.

### 2. Primitive linkage and runtime graph resolution are distinct

**Sources**
- Claude, **Introducing dynamic workflows in Claude Code** (2026-05-28): https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- Claude, **A harness for every task: dynamic workflows in Claude Code** (2026-06-02): https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code
- Cursor, **What we've learned building cloud agents** (2026-06-02): https://cursor.com/blog/cloud-agent-lessons

**Requirements**
- Primitive validation MUST determine whether an executable has its required injectable dependencies.
- Graph resolution MUST separately determine whether the final runtime-composed graph has satisfiable edges, contracts, permissions, models, tools, environment capabilities and termination paths.
- Runtime-composed graphs MUST support a pre-execution resolution phase after final configuration is known.
- Detectable missing/incompatible linkage MUST fail before substantive execution.
- Diagnostics SHOULD identify the unsatisfied edge/capability and candidate provider rather than surface an arbitrary downstream failure.

This permits template subgraphs to remain intentionally partial until instantiated.

### 3. Dynamic subgraphs are first-class

**Sources**
- Claude, **Introducing dynamic workflows in Claude Code** (2026-05-28): https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- Claude, **A harness for every task: dynamic workflows in Claude Code** (2026-06-02): https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code

**Requirements**
- A node MAY instantiate a subordinate graph at runtime.
- Dynamic subgraphs MUST have explicit input/output contracts and execution budgets.
- Fan-out, aggregation, independent review, adversarial/refutation passes and iterative repair SHOULD be reusable graph patterns.
- Runtime-generated graphs MUST undergo the same linkage, capability, security and termination validation as static graphs.
- Dynamic subgraphs SHOULD remain observable as graph executions rather than opaque nested model calls.
- Reusable template subgraphs SHOULD be parameterized rather than cloned into task-specific code.

### 4. Repeating execution requires an explicit stop contract

**Sources**
- Claude, **Loop engineering: Getting started with loops** (2026-06-30): https://claude.com/blog/getting-started-with-loops

**Requirements**
Every repeating graph/subgraph MUST expose a trigger, continuation condition, success/stop condition, failure/abort condition, progress signal, carried state, and applicable iteration/time/token/cost budgets. A loop without a bounded or externally resolvable stop condition SHOULD fail validation unless explicitly declared a persistent service loop.

### 5. Verification is part of execution

**Sources**
- Claude, **Building verification loops in Claude Code with skills** (2026-07-22): https://claude.com/blog/building-verification-loops-in-claude-code-with-skills
- Claude, **How Anthropic runs large-scale code migrations with Claude Code** (2026-07-16): https://claude.com/blog/ai-code-migration
- Claude, **Agentic coding is straining CI. Here's how we scaled test impact analysis at Anthropic** (2026-09-14): https://claude.com/blog/agentic-coding-is-straining-ci-heres-how-we-scaled-test-impact-analysis-at-anthropic

**Requirements**
- Verification SHOULD be an explicit graph phase or injectable policy.
- Deterministic verification SHOULD be preferred when a deterministic oracle exists.
- Evaluator-model verification SHOULD use isolated context where independence matters.
- Verification results MUST be structured enough to route repair.
- Completion MUST be able to depend on verification state; "answer generated" and "task complete" are distinct.
- VerificationPolicy SHOULD support impact-based selection and choose the smallest sufficient verification set when dependency/confidence information permits.
- High-consequence changes MAY force exhaustive verification.
- Verification cost, latency, failures and marginal detection value SHOULD be observable.


### 6. Context is scoped, provenance-bearing and discovered on demand

**Sources**
- Claude, **How and when to use subagents in Claude Code** (2026-04-07): https://claude.com/blog/subagents-in-claude-code
- Claude, **The new rules of context engineering for Claude 5 generation models** (2026-07-24): https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models
- Cursor, **Dynamic context discovery** (2026-01-06): https://cursor.com/blog/dynamic-context-discovery

**Requirements**
- Context MUST carry explicit scope and provenance.
- Child execution SHOULD receive the minimum context required by its contract; parent history MUST NOT automatically flow into children.
- Child results SHOULD return contracted synthesis rather than entire working context by default.
- ContextProvider SHOULD expose discoverable descriptions/indices before loading large payloads.
- Large context SHOULD normally be retrieved just in time, with size/token cost exposed where practical.
- Static instructions SHOULD be separated from task-specific retrieved context.
- Context consumption SHOULD be observable and attributable to providers.

For June, vector/KG memory is therefore a context provider, not permission to dump remembered material into every turn.

### 7. Delegation requires capability boundaries and measurable coordination cost

**Sources**
- Claude, **How and when to use subagents in Claude Code** (2026-04-07): https://claude.com/blog/subagents-in-claude-code
- Cursor, **Subagents, Skills, and Image Generation** (2026-01-22): https://cursor.com/changelog/2-4
- Cursor, **Improved token efficiency for longer agent runs** (2026-09-23): https://cursor.com/blog/improved-token-efficiency

**Requirements**
- Delegated execution SHOULD use a CapabilityEnvelope covering model class, tools, permissions, context providers, resource budget, output contract and escalation policy.
- Children MUST NOT inherit parent capabilities implicitly.
- DelegationPolicy SHOULD choose inline versus child/subgraph execution based on dependency structure, context pollution, parallelism, independence, latency, compute and coordination cost.
- Telemetry SHOULD measure duplicated work, stale-task execution, synchronization overhead and unused child results.
- Parents SHOULD be able to cancel/supersede child work invalidated by upstream state.
- Child contracts SHOULD carry a parent-state/version identifier when staleness matters.

### 8. Skills and injectables should contain scarce information

**Sources**
- Claude, **Lessons from building Claude Code: How we use skills** (2026-06-03): https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills
- Claude, **Steering Claude Code: when to use CLAUDE.md, skills, hooks, and subagents** (2026-06-18): https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more

**Requirements**
- Instruction bundles SHOULD optimize for information gain rather than completeness.
- Components SHOULD distinguish invariants, domain knowledge, procedures and learned gotchas.
- Gotchas SHOULD be independently appendable/versionable.
- Component trigger/use rates SHOULD be measurable; under-triggering and over-triggering SHOULD be evaluable failure modes.
- Repeated June failures MAY propose new gotchas during sleep/dreaming, but promotion to active policy SHOULD pass evaluation.

### 9. Soft guidance and hard enforcement are different mechanisms

**Sources**
- Claude, **Steering Claude Code: when to use CLAUDE.md, skills, hooks, and subagents** (2026-06-18): https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more
- Claude, **How Anthropic secures its AI-native software development lifecycle** (2026-07-21): https://claude.com/blog/how-anthropic-secures-its-ai-native-software-development-lifecycle
- Cursor, **Implementing a secure sandbox for local agents** (2026-02-18): https://cursor.com/blog/agent-sandboxing

**Requirements**
MechaHarness SHOULD distinguish advisory context, behavioral instruction, executable hook/policy, capability/permission boundary and deterministic invariant. Security/correctness requirements that can be mechanically enforced MUST NOT depend solely on prompt compliance.

### 10. Independent review requires genuinely independent state

**Sources**
- Claude, **How Anthropic runs large-scale code migrations with Claude Code** (2026-07-16): https://claude.com/blog/ai-code-migration
- Claude, **A harness for every task: dynamic workflows in Claude Code** (2026-06-02): https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code

**Requirements**
- Independent review MUST create a context boundary, not merely ask the producer to reconsider in the same accumulated state.
- Reviewers SHOULD receive the artifact, acceptance contract and necessary evidence while omitting producer reasoning unless required.
- Multiple reviewers MAY be aggregated deterministically, by a judge, or by another graph.
- Disagreement SHOULD be retained as data rather than prematurely collapsed.

### 11. Fix the process that produced the failure

**Sources**
- Claude, **How Anthropic runs large-scale code migrations with Claude Code** (2026-07-16): https://claude.com/blog/ai-code-migration
- Cursor, **Continually improving our agent harness** (2026-04-30): https://cursor.com/blog/continually-improving-agent-harness

**Requirements**
- Traces MUST preserve enough structure to attribute failures to graph topology, routing, context, tools, models or evaluator policy.
- Repeated failure classes SHOULD be detectable across runs.
- Proposed harness changes SHOULD be evaluable against retained historical cases.
- June SHOULD prefer improving reusable process components over memorizing one-off output corrections.

### 12. Long-running work requires resumable external state

**Sources**
- Claude, **Introducing dynamic workflows in Claude Code** (2026-05-28): https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- Cursor, **Introducing Projects** (2026-09-10): https://cursor.com/blog/projects

**Requirements**
- Long-running graph state MUST be serializable independently of model context.
- Runs SHOULD resume from durable checkpoints without replaying successful expensive work.
- Checkpoints MUST identify graph/component versions, inputs, completed nodes, pending work and relevant side effects.
- Resume MUST detect incompatible graph/config changes instead of silently continuing with altered semantics.


### 13. Model routing optimizes an outcome frontier

**Sources**
- Claude, **How and when to use subagents in Claude Code** (2026-04-07): https://claude.com/blog/subagents-in-claude-code
- Cursor, **How we compare model quality in Cursor** (2026-03-11): https://cursor.com/blog/cursorbench
- Cursor, **Continually improving our agent harness** (2026-04-30): https://cursor.com/blog/continually-improving-agent-harness

**Requirements**
- Model selection MUST be injectable at graph and node/subgraph level.
- Nodes SHOULD declare capability needs instead of hard-coding model identity where practical.
- Routing SHOULD consider correctness together with latency, context size, memory pressure, energy/compute and monetary cost where relevant.
- Model switching inside accumulated context SHOULD account for context-transfer/cache cost and semantic loss.
- Fresh specialized child execution MAY be preferable to mid-context model replacement.
- Escalation from a smaller worker to a larger reasoning model SHOULD be representable as policy.

### 14. Harness changes are hypotheses requiring online and offline evidence

**Sources**
- Cursor, **Continually improving our agent harness** (2026-04-30): https://cursor.com/blog/continually-improving-agent-harness
- Cursor, **How we compare model quality in Cursor** (2026-03-11): https://cursor.com/blog/cursorbench

**Requirements**
- A harness change SHOULD be expressible as a testable hypothesis with expected affected metrics.
- MechaHarness SHOULD support replay/offline evaluation plus production/online telemetry.
- Evaluation SHOULD be multidimensional where correctness, latency, compute/token use, tool churn or interaction behavior can trade off.
- Eval corpora SHOULD evolve with real workloads rather than freeze into a benchmark.
- Harness versions and experiment assignments SHOULD be recorded in traces.

This is the MechaHarness "test kitchen": observe a failure or opportunity, form a harness hypothesis, evaluate it, retain improvements and retire regressions.

### 15. Autonomy is risk-scaled, not binary

**Sources**
- Cursor, **Governing agent autonomy with Auto-review** (2026-06-11): https://cursor.com/blog/agent-autonomy-auto-review
- Cursor, **Implementing a secure sandbox for local agents** (2026-02-18): https://cursor.com/blog/agent-sandboxing
- Claude, **How Anthropic secures its AI-native software development lifecycle** (2026-07-21): https://claude.com/blog/how-anthropic-secures-its-ai-native-software-development-lifecycle

**Requirements**
- Permission policy SHOULD classify actions by consequence/risk rather than globally enable/disable autonomy.
- Low-risk actions MAY proceed under structural sandbox constraints without repeated approval.
- Crossing declared trust boundaries SHOULD trigger stronger verification, narrower capabilities, explicit approval or denial according to policy.
- Approval frequency SHOULD be treated as a safety/usability metric because excessive prompting degrades meaningful review.

### 16. The execution environment is part of the linkage contract

**Sources**
- Cursor, **What we've learned building cloud agents** (2026-06-02): https://cursor.com/blog/cloud-agent-lessons
- Cursor, **Cursor agents can now control their own computers** (2026-02-24): https://cursor.com/blog/agent-computer-use

**Requirements**
- Environment capabilities and health MUST be discoverable before dependent graph work executes.
- Missing secrets, routes, binaries, resource capacity and incompatible runtime state SHOULD become structured linkage/environment failures where possible.
- Environment repair MAY itself be a bounded subgraph.
- Environment identity/version SHOULD be durable execution provenance.

### 17. Persistent goals and event-triggered execution are not long chat turns

**Sources**
- Cursor, **Build agents that run automatically** (2026-03-05): https://cursor.com/blog/automations
- Cursor, **Introducing Projects** (2026-09-10): https://cursor.com/blog/projects
- Cursor, **Cloud Agents and Cursor Harness Improvements** (2026-08-19): https://cursor.com/changelog/08-19-26

**Requirements**
- A goal MUST be able to outlive a conversational session.
- Graph execution MAY wake from schedules, events, external state changes or child completion.
- Persistent goals SHOULD store their own state, completion contract, subscriptions/triggers and graph checkpoint.
- Event handling SHOULD re-resolve relevant linkage/environment state before resuming.
- Conversational steering SHOULD update running goals at defined safe boundaries rather than necessarily abort current atomic work.

For June, reminders, monitoring, background research, maintenance and sleep/dreaming become persistent goals rather than pretend conversations.

### 18. Advisor is sparse, non-binding reasoning escalation

**Sources**
- Claude Code Docs, **Escalate hard decisions with the advisor tool** (reviewed 2026-09-29): https://code.claude.com/docs/en/advisor

**Requirements**
- MechaHarness SHOULD expose an `Advisor` and/or `AdvisorPolicy` distinct from delegation and model replacement.
- The active executor MUST retain task ownership; advisor output is non-binding guidance.
- Advisor model/provider selection SHOULD be injectable and capability-routed.
- AdvisorPolicy SHOULD support sparse triggers such as consequential planning, repeated failure, unresolved hypotheses, uncertainty/evaluator thresholds and high-consequence completion.
- Invocation MAY be model-, policy-, graph- or user-initiated.
- Advisor input MUST use an explicit context contract. Full history MAY be supplied, but scoped summaries, evidence, traces, artifacts and retrieved state SHOULD also be supported.
- Output SHOULD structure recommendations, uncertainty, assumptions, requested evidence and proposed next actions.
- Executors MUST be able to reject/adapt advice when evidence contradicts it; disagreement SHOULD remain in the trace.
- Advisor compatibility SHOULD participate in runtime linkage resolution.
- Advisor use MUST be observable: trigger, advisor, supplied context, latency/resource cost, response, whether advice was followed and eventual outcome.
- Effectiveness SHOULD be evaluable against equivalent execution without consultation.
- Policies SHOULD support budgets/rate limits and avoid low-value routine consultation.
- Optional-advisor failure MUST have an explicit fallback policy.

**Architectural distinction:** a subagent owns delegated work; an advisor observes a decision state and returns counsel while the caller retains ownership. Model escalation replaces/upgrades the executor; advising lets the existing executor continue while purchasing stronger or specialized reasoning only at selected boundaries.

For June this permits a small/medium local worker to preserve task continuity while consulting a larger reasoning model sparsely. It is also a natural future target for a small learned/Jev-like policy deciding whether consultation is worth its marginal cost.

## Candidate reusable primitives

- `LinkageResolver` — validates final runtime graph wiring and substrate capabilities.
- `CapabilityEnvelope` — tools, permissions, context, model class and budgets available to an execution.
- `StopContract` — continuation, success, abort and resource limits for repeating work.
- `VerificationPolicy` — selects and executes appropriate verification.
- `ContextProvider` — lazily supplies scoped, provenance-bearing context.
- `DelegationPolicy` — chooses inline versus child/subgraph execution.
- `Reviewer` / `Adversary` — isolated verification roles with explicit evidence contracts.
- `CheckpointStore` — durable graph execution state.
- `OutcomeContract` — machine-readable satisfactory-completion definition.
- `HarnessExperiment` — A/B or hill-climb comparison of orchestration changes.
- `Advisor` — accepts structured decision state and returns non-binding guidance.
- `AdvisorPolicy` — decides whether consultation is warranted, required capability and supplied context.

These SHOULD normally be interfaces/protocols rather than framework-mandated concrete implementations.

