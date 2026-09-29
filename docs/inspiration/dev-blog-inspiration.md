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

