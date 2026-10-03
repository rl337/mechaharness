# Developer Blog Inspiration for MechaHarness

> Living design-notes document for the reusable MechaHarness execution library. External developer material is evidence and inspiration, not specification. Host/client orchestrators may keep companion design notes outside this repository.

Last reviewed: 2026-10-03

## Purpose

This document tracks useful agent-harness ideas from Claude/Anthropic and Cursor and translates them into testable requirements for the reusable MechaHarness execution library. It is deliberately provenance-heavy: every inspiration-derived requirement names the source material that motivated it. The goal is not product compatibility. It is to challenge MechaHarness assumptions against production agent systems and retain only patterns that generalize.

## Ownership boundary with client orchestrators

MechaHarness owns reusable execution vocabulary and mechanisms: primitives, injectable protocols, graph execution semantics, runtime linkage/validation, capability envelopes, context-provider interfaces, verification/delegation/advisor policies, durable execution contracts, generic observability/evaluation hooks, and **parameterized reusable graph-template definitions**. Generic patterns such as fan-out/aggregate, verify/repair, independent review, and environment repair belong here when they are useful beyond a single host app.

A client orchestrator owns scheduling, task lifecycle, document management, knowledge-graph operation, issue/work tracking, persistent goals, product policy, provider implementations, and the decision about **which MechaHarness templates to instantiate, bind, sequence, schedule, and compose**.

The ownership boundary is between **abstract reusable template definitions** and **concrete executable graph realizations**. A MechaHarness template is intentionally incomplete: it exposes soft points for tools, providers, prompts/skills, model capabilities, budgets, persistence adapters, policies, task state, and other client-specific bindings. Client code may instantiate that template, fill those soft points, add host-specific nodes or composition, and retain the resulting executable graph or workflow definition in the client repository. The fact that MechaHarness executes or validates that graph does not transfer ownership of the client-specific realization back into the library.

A host-specific graph pattern MAY incubate entirely in the client while its shape is still coupled to that application's semantics. When repeated evidence shows a stable, reusable structure, its generic skeleton SHOULD be extracted into MechaHarness and host assumptions converted into explicit parameters/providers/contracts. The client then consumes the promoted template. The reverse is also valid: a purportedly generic MechaHarness template that proves application-specific SHOULD be simplified, deprecated, or moved back toward the client boundary rather than preserved as accidental framework policy.

A host requirement may therefore motivate a generic MechaHarness capability, but this document SHOULD state the reusable interface rather than encode host-specific workflow policy.

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

Client orchestrators SHOULD be able to absorb or retire scaffolding as model capability changes without requiring task semantics to be rewritten.

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

A client knowledge graph or document system is therefore a ContextProvider implementation rather than permission for MechaHarness to own application memory policy.

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
- Repeated client failures MAY propose new gotchas (for example during offline consolidation), but promotion to active policy SHOULD pass evaluation.

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
- Clients SHOULD prefer improving reusable process components over memorizing one-off output corrections.

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

Persistent-goal ownership belongs to the client orchestrator. MechaHarness SHOULD provide resumable execution and event-compatible contracts that a client can invoke when a goal wakes.

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

This permits a client to preserve executor continuity while consulting a larger reasoning model sparsely. The generic consultation decision is also a natural target for a small learned policy deciding whether advice is worth its marginal cost.

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


### 19. Template incubation and promotion are evidence-driven

**Sources**
- Claude, **Introducing dynamic workflows in Claude Code** (2026-05-28): https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- Claude, **A harness for every task: dynamic workflows in Claude Code** (2026-06-02): https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code
- Cursor, **Continually improving our agent harness** (2026-04-30): https://cursor.com/blog/continually-improving-agent-harness

**Requirements**
- A reusable `GraphTemplate` SHOULD expose explicit soft points rather than embed client-specific tools, providers, prompts, models, persistence, product policy or durable application state.
- Template instantiation SHOULD be able to produce a concrete executable graph whose client-specific bindings remain owned by the client repository.
- MechaHarness MUST be able to validate and execute such client-owned concrete graphs without requiring their application bindings or workflow definitions to move into MechaHarness.
- A graph/workflow MAY incubate entirely in a client while its topology and semantics are still application-specific or unstable.
- Repeated successful use, repeated duplication, or evidence of a stable generic topology SHOULD trigger an abstraction review rather than automatic promotion.
- Promotion into MechaHarness SHOULD extract only the reusable skeleton and convert client assumptions into explicit parameters, providers, contracts or policy hooks.
- Promotion SHOULD preserve provenance and tests connecting the original client workflow to the extracted template so behavior drift can be detected.
- A MechaHarness template that later proves application-specific SHOULD be eligible for deprecation, simplification or demotion rather than becoming permanent framework scaffolding.

This creates a deliberate incubation path: **client concrete graph → observed stable pattern → abstract reusable template → MechaHarness → client rebinds the promoted template**.

### 20. Lifecycle interception and replaceable extensions are first-class

**Sources**
- Claude, **How Anthropic's sales team rebuilt inbound with Claude Managed Agents** (2026-09-30): https://claude.com/blog/how-anthropics-sales-team-rebuilt-inbound-with-claude-managed-agents
- Claude, **Customize Claude Code with mods** (2026-10-01): https://claude.com/blog/claude-code-mods

**Requirements**
- MechaHarness SHOULD expose typed lifecycle events at stable execution boundaries where extensions can observe or alter behavior without patching the core executor.
- An extension point SHOULD declare which interception modes it permits, including observation before/after an event and, only where safe, rewriting, retrying, replacing, blocking, or wrapping the default behavior.
- Multiple extensions targeting the same lifecycle event MUST have deterministic, inspectable ordering; ordering MUST NOT depend on incidental discovery or import order.
- Extensions MUST declare the capabilities and authority they require. An extension MUST NOT silently widen the tool, permission, context, model, filesystem, network, or credential envelope granted to the underlying execution.
- Framework security invariants and host-supplied hard-deny policy MUST take precedence over ordinary replaceable extensions. Extension ordering MUST NOT permit a later or less-trusted extension to bypass a stronger invariant.
- Traces SHOULD record extension identity/version, lifecycle event, ordering, inputs/outputs affected, retries/replacements, and whether default behavior ran so extension-induced failures can be attributed.
- Built-in scaffolding MAY migrate into replaceable extensions when doing so reduces the irreducible core without weakening contracts or safety boundaries.
- Replaceable built-ins and extensions SHOULD participate in the same hypothesis, versioning, evaluation, rollback, and retirement lifecycle as other harness scaffolding. New model/runtime capability SHOULD trigger tests for whether an extension remains necessary.
- Client orchestrators MAY provide application-specific extensions through this interface, but MechaHarness MUST own only the generic interception contract, ordering semantics, capability enforcement, and observability rather than the client's application policy.
- Escalation or hand-off events SHOULD be representable as structured outcomes that clients can mine as feedback, without embedding domain-specific escalation policy in MechaHarness.

**Architectural tension:** replacement hooks increase adaptability but can turn the harness into an implicit second graph if arbitrary extensions rewrite control flow. MechaHarness SHOULD keep extension interception local to declared lifecycle events; multi-step orchestration and durable workflow topology SHOULD remain explicit graph structure.

## Client-orchestrator interface implications

MechaHarness SHOULD make it possible for a client orchestrator to:
1. Keep ordinary turns cheap when complex graph execution is unnecessary.
2. Spawn focused child/tool executions without automatically contaminating parent context.
3. Instantiate reusable parameterized graph templates after tools, models, providers, permissions and environment are known, producing concrete client-owned executable graphs from those bindings.
4. Perform final runtime linkage validation before material execution.
5. Scale verification with consequence and uncertainty.
6. Persist execution/checkpoint state independently of model context.
7. Mine structured traces externally for recurring failure classes and proposed policy changes.
8. Evaluate proposed harness changes against retained cases before promotion.
9. Re-evaluate and retire obsolete scaffolding after model/runtime upgrades.
10. Enforce security boundaries structurally despite model confusion or prompt injection.
11. Consult sparse Advisors without transferring task ownership.

The scheduler, task runner, persistent-goal store, document manager, knowledge graph, issue tracker, and concrete host orchestration remain outside this library.

## Monitoring protocol

When refreshing this document:
1. Read the current canonical file from `main` first.
2. Enumerate new Claude/Anthropic developer-blog entries, relevant Claude Code documentation changes, and Cursor developer-blog entries since `Last reviewed`.
3. Prefer material concerning harnesses, loops/graphs, tools, context, skills, subagents, model routing, advisors/escalation, verification/evals, memory, security, autonomy, execution environments, long-running work and self-improvement.
4. Read relevant sources rather than relying on title/snippet.
5. Compare each idea with existing MechaHarness requirements.
6. Add only net-new requirements, meaningful refinements, contradictions, retirements, or evidence that materially changes priority.
7. Every changed requirement MUST name its material source(s), date when available, and canonical URL.
8. Generalize product mechanics only when they map cleanly to MechaHarness.
9. Prefer testable MUST/SHOULD/MAY statements.
10. If no material document change exists, create no branch, commit or PR.
11. If material change exists, create a branch from current `main`, update this file, verify the diff is non-empty, and open a **draft PR**.
12. The PR body MUST identify triggering sources, summarize proposed requirements/refinements/retirements, explain relevance to MechaHarness and any client-interface implication, and call out uncertainty or architectural tension.
13. Future updates after this bootstrap SHOULD be incremental.

## Source ledger: Claude / Anthropic

Reviewed through 2026-09-29:

- **Agent Harness Design: 3 Patterns for Harnessing Claude's Intelligence** — 2026-04-02 — https://claude.com/blog/harnessing-claudes-intelligence
- **How and when to use subagents in Claude Code** — 2026-04-07 — https://claude.com/blog/subagents-in-claude-code
- **Seeing like an agent: how we design tools in Claude Code** — 2026-04-10 — https://claude.com/blog/seeing-like-an-agent
- **Introducing dynamic workflows in Claude Code** — 2026-05-28 — https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- **A harness for every task: dynamic workflows in Claude Code** — 2026-06-02 — https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code
- **Lessons from building Claude Code: How we use skills** — 2026-06-03 — https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills
- **Running an AI-native engineering org** — 2026-06-03 — https://claude.com/blog/running-an-ai-native-engineering-org
- **Steering Claude Code: when to use CLAUDE.md, skills, hooks, and subagents** — 2026-06-18 — https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more
- **Loop engineering: Getting started with loops** — 2026-06-30 — https://claude.com/blog/getting-started-with-loops
- **How Anthropic runs large-scale code migrations with Claude Code** — 2026-07-16 — https://claude.com/blog/ai-code-migration
- **How Anthropic secures its AI-native software development lifecycle** — 2026-07-21 — https://claude.com/blog/how-anthropic-secures-its-ai-native-software-development-lifecycle
- **How Datadog built a "universal machine tool" for Claude Code** — 2026-07-21 — https://claude.com/blog/how-datadog-built-a-universal-machine-tool-for-claude-code
- **Building verification loops in Claude Code with skills** — 2026-07-22 — https://claude.com/blog/building-verification-loops-in-claude-code-with-skills
- **The new rules of context engineering for Claude 5 generation models** — 2026-07-24 — https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models
- **Agentic coding is straining CI. Here's how we scaled test impact analysis at Anthropic** — 2026-09-14 — https://claude.com/blog/agentic-coding-is-straining-ci-heres-how-we-scaled-test-impact-analysis-at-anthropic
- **Coding sessions are longer and use more context. Claude Opus 5.5 is built with that in mind.** — 2026-09-24 — https://claude.com/blog/claude-opus-5-5-built-for-coding-sessions-that-use-more-context
- **Escalate hard decisions with the advisor tool** — Claude Code Docs, reviewed 2026-09-29 — https://code.claude.com/docs/en/advisor
- **How Anthropic's sales team rebuilt inbound with Claude Managed Agents** — 2026-09-30 — https://claude.com/blog/how-anthropics-sales-team-rebuilt-inbound-with-claude-managed-agents
- **Customize Claude Code with mods** — 2026-10-01 — https://claude.com/blog/claude-code-mods

Watch source: https://claude.com/blog-category/claude-code

## Source ledger: Cursor

Reviewed through 2026-09-29:

- **Dynamic context discovery** — 2026-01-06 — https://cursor.com/blog/dynamic-context-discovery
- **Subagents, Skills, and Image Generation** — 2026-01-22 — https://cursor.com/changelog/2-4
- **Implementing a secure sandbox for local agents** — 2026-02-18 — https://cursor.com/blog/agent-sandboxing
- **Cursor agents can now control their own computers** — 2026-02-24 — https://cursor.com/blog/agent-computer-use
- **Build agents that run automatically** — 2026-03-05 — https://cursor.com/blog/automations
- **How we compare model quality in Cursor** — 2026-03-11 — https://cursor.com/blog/cursorbench
- **Continually improving our agent harness** — 2026-04-30 — https://cursor.com/blog/continually-improving-agent-harness
- **What we've learned building cloud agents** — 2026-06-02 — https://cursor.com/blog/cloud-agent-lessons
- **Governing agent autonomy with Auto-review** — 2026-06-11 — https://cursor.com/blog/agent-autonomy-auto-review
- **Cloud Agents and Cursor Harness Improvements** — 2026-08-19 — https://cursor.com/changelog/08-19-26
- **Introducing Projects** — 2026-09-10 — https://cursor.com/blog/projects
- **Improved token efficiency for longer agent runs** — 2026-09-23 — https://cursor.com/blog/improved-token-efficiency

Watch source: https://cursor.com/blog

## Provenance note

This first version is intentionally broad: it establishes the 0-to-1 baseline accumulated from the reviewed Claude/Anthropic and Cursor material. Subsequent changes should be much smaller and should make it easy to trace a source article to the specific MechaHarness requirement it changes.
