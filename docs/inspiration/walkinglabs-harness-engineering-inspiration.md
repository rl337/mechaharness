# WalkingLabs Harness Engineering inspiration for MechaHarness

> Living attribution and gap-analysis document for ideas drawn from the
> [Learn Harness Engineering](https://walkinglabs.github.io/learn-harness-engineering/en/)
> online book by WalkingLabs.
>
> External material is inspiration and evidence, not specification. The goal is
> to preserve provenance for each proposed MechaHarness refinement while
> translating coding-agent-specific advice into reusable library mechanisms.

Last reviewed: 2026-10-04

## Scope and method

This review re-spidered the English edition rather than reusing a prior summary.
The scan covered all fourteen lectures, all eight progressive projects, the
resource/template library, and the four frontier harness design breakdowns:
Pi, Claude Code, Codex, and DeepSeek Harness.

For every actionable design claim ("oracle point"), this document records the
exact WalkingLabs permalink, the closest current MechaHarness mechanism, a
coverage verdict, and a recommendation that preserves the library/client
ownership boundary.

Coverage labels:

- **covered** — a first-class mechanism exists and no material change is needed.
- **strengthen** — the mechanism exists but a useful invariant or integration is missing.
- **gap** — a reusable mechanism appears absent.
- **client-owned** — the concern belongs in June or another host; MechaHarness
  should expose only the reusable seam.

WalkingLabs primarily teaches coding-agent workspaces. MechaHarness is a
reusable execution library. Project task stores, schedules, issue trackers,
product goals, document stores, and concrete workflow realizations therefore
remain client-owned. MechaHarness owns reusable execution semantics, policies,
graph templates, capability seams, linkage, verification, observability, and
lifecycle contracts.

## Source index

Lectures:

1. [L01 — Strong Models Don't Mean Reliable Execution](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-01-why-capable-agents-still-fail/)
2. [L02 — What a Harness Actually Is](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-02-what-a-harness-actually-is/)
3. [L03 — Repository as System of Record](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-03-why-the-repository-must-become-the-system-of-record/)
4. [L04 — Split Instructions Across Files](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-04-why-one-giant-instruction-file-fails/)
5. [L05 — Keeping Context Alive Across Sessions](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-05-why-long-running-tasks-lose-continuity/)
6. [L06 — Initialization as Its Own Phase](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-06-why-initialization-needs-its-own-phase/)
7. [L07 — Draw Clear Task Boundaries](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-07-why-agents-overreach-and-under-finish/)
8. [L08 — Feature Lists as Harness Primitives](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-08-why-feature-lists-are-harness-primitives/)
9. [L09 — Prevent Premature Victory](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-09-why-agents-declare-victory-too-early/)
10. [L10 — Full Pipeline Verification](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-10-why-end-to-end-testing-changes-results/)
11. [L11 — Runtime Observability](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/)
12. [L12 — Clean Session Handoffs](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/)
13. [L13 — Autonomous Loops](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-13-loop-engineering/)
14. [L14 — Graph Engineering](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/)

Projects:

- [P01 — Prompt-Only vs Rules-First](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-01-baseline-vs-minimal-harness/)
- [P02 — Agent-Readable Workspace](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-02-agent-readable-workspace/)
- [P03 — Multi-Session Continuity](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-03-multi-session-continuity/)
- [P04 — Runtime Feedback and Scope Control](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-04-incremental-indexing/)
- [P05 — Self-Verification and Role Separation](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-05-grounded-qa-verification/)
- [P06 — Complete Harness / Observability](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-06-runtime-observability-and-debugging/)
- [P07 — First Automated Loop](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-07-loop-engineering-first-loop/)
- [P08 — First Explicit Graph](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/)

Frontier breakdowns:

- [Pi](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/pi/)
- [Claude Code](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/claude-code/)
- [Codex](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/codex/)
- [DeepSeek Harness](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/deepseek/)

Resource library:

- [Templates and resources](https://walkinglabs.github.io/learn-harness-engineering/en/resources/templates/)

---

## Oracle matrix

### 1. Diagnose the harness before blaming the model

**Source:** [L01](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-01-why-capable-agents-still-fail/)

WalkingLabs attributes failures first to specification, context, environment,
verification, or state. MechaHarness already has structured failure attribution
across graph topology, routing, context, tools, models, evaluator policy,
linkage, and environment.

**Verdict:** **strengthen**

Expand failure attribution beyond error-prefix classification so records can
carry failed invariant, causal evidence refs, responsible node/layer, and
recommended repair target. Keep "model" as one explicit category rather than a
default explanation.

### 2. Ablate harness components to learn what is load-bearing

**Source:** [L02](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-02-what-a-harness-actually-is/)

MechaHarness already has harness experiments, research hypotheses, and
scaffolding retirement.

**Verdict:** **strengthen**

Add a standard component-ablation experiment shape: baseline harness
fingerprint, disabled component IDs, matched task corpus, quality/success/cost/
latency deltas, and confidence metadata. Results should be valid evidence for
promoting, weakening, or retiring soft points and extensions.

### 3. Treat harness debt like code debt

**Source:** [L02](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-02-what-a-harness-actually-is/), [L12](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/)

MechaHarness has experiment and template-incubation machinery but no generic
harness-health artifact.

**Verdict:** **strengthen**

Add an optional HarnessHealthSnapshot schema for unused extensions, dead soft
points, stale bindings, unexercised graph routes, recurring linkage warnings,
and ablation evidence. Cleanup scheduling stays client-owned.

### 4. Keep authoritative state outside conversation

**Source:** [L03](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-03-why-the-repository-must-become-the-system-of-record/)

GraphStore/EventLog, DecisionLog, checkpoints, and durable refs already provide
the reusable mechanisms. Application document/task stores remain host-owned.

**Verdict:** **covered / client-owned**

Do not add a repository or issue tracker to the library. Require durable,
provenance-bearing references to host state rather than literal git storage.

### 5. Minimize discovery cost and track knowledge freshness

**Source:** [L03](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-03-why-the-repository-must-become-the-system-of-record/)

ContextProvider already supports index-before-load, provenance, scoping, and
token estimates.

**Verdict:** **strengthen**

Add optional freshness, last-verified, authority, and expected-load-cost
metadata. Let selection policy optimize relevance plus discovery cost and
surface stale-context evidence instead of silently using it.

### 6. Apply ACID-like semantics to execution state

**Source:** [L03](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-03-why-the-repository-must-become-the-system-of-record/)

Checkpoints, recovery boundaries, base revisions, write scopes, stale
preconditions, and merge conflict policy already cover much of this.

**Verdict:** **strengthen**

Add an optional StateTransactionContract containing preconditions, commit
predicates, write scopes, conflict policy, rollback/compensation behavior, and
durable checkpoint boundary. Verification success can act as the consistency
predicate.

### 7. Entry instructions are a router, not an encyclopedia

**Source:** [L04](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-04-why-one-giant-instruction-file-fails/), [Codex](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/codex/)

Instruction components exist, but a full hierarchical selection model is not
surfaced.

**Verdict:** **strengthen**

Give instruction components scope/applicability, priority/authority, source
provenance, optional expiry/review conditions, and estimated context cost. Use
"map first, details on demand" without baking AGENTS.md into the library.

### 8. Load instructions/context close to where they apply

**Source:** [L04](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-04-why-one-giant-instruction-file-fails/), [Claude Code](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/claude-code/)

Lazy scoped ContextProvider support exists, but the current requirements map
notes the default harness path does not always use providers.

**Verdict:** **strengthen**

Make node-level context projection a normal inference step. Nodes should
declare context/instruction needs and lazy providers should be the default
assembly path.

### 9. Compaction should be staged and pluggable

**Source:** [L05](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-05-why-long-running-tasks-lose-continuity/), [Claude Code](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/claude-code/), [Pi](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/pi/)

Scoped context exists, but no generic staged compaction strategy is prominent.

**Verdict:** **gap**

Add a pluggable ContextCompactionStrategy with lossless pruning/deduplication,
structured extraction/distillation, then optional lossy summarization. Preserve
provenance and record which information classes were discarded.

### 10. Preserve "why", not only "what", across resets

**Source:** [L05](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-05-why-long-running-tasks-lose-continuity/)

DecisionLog and graph evidence can preserve rationale, but no handoff contract
requires it.

**Verdict:** **strengthen**

Define a reusable HandoffRecord containing completed/pending work, verification
state, decisions, rationale, rejected alternatives, risks, and next executable
action. Hosts own storage.

### 11. Make resume cost observable

**Source:** [L05](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-05-why-long-running-tasks-lose-continuity/)

Durable resume and fingerprint refusal are implemented.

**Verdict:** **strengthen**

Emit resume metrics: wake-to-first-productive-node time, tokens/tools spent
rebuilding context, provider loads, revalidation work, and replayed events.

### 12. Initialization deserves an explicit phase

**Source:** [L06](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-06-why-initialization-needs-its-own-phase/)

Linkage resolution, environment probes, environment-repair, and fingerprint
validation cover much of preflight readiness but not as one contract.

**Verdict:** **strengthen**

Add a reusable initialize/preflight graph template that performs linkage,
environment/capability checks, baseline verification, checkpoint compatibility,
and readiness output before substantive nodes can run.

### 13. Safe handoff boundaries should be runtime invariants

**Source:** [L06](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-06-why-initialization-needs-its-own-phase/), [L12](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/)

Checkpointing exists, but "handoff ready" is not a generic predicate.

**Verdict:** **strengthen**

Allow graphs to mark safe handoff boundaries requiring reconstructable pending
work, durable evidence refs, compatible linkage fingerprint, and no ambiguous
unrecorded side effects.

### 14. Bound WIP and apply back-pressure

**Source:** [L07](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-07-why-agents-overreach-and-under-finish/), [L08](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-08-why-feature-lists-are-harness-primitives/)

Dependencies and budgets constrain execution, but no first-class WIP/concurrency
policy surfaced in the current library.

**Verdict:** **gap**

Add a WorkInProgressPolicy/scheduler concurrency policy limiting active nodes by
graph, resource class, write scope, consequence, or host work group. Do not
hard-code WIP=1; it is a safe coding-agent default, not a universal truth.

### 15. Task state transitions must be verified, not self-declared

**Source:** [L08](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-08-why-feature-lists-are-harness-primitives/)

OutcomeContract, VerificationPolicy, node status, and verification helpers
already separate generation from verified completion.

**Verdict:** **covered**

Keep client-owned state transitions evidence-gated when their outcome contract
requires verification.

### 16. The task store is client-owned; the transition contract is reusable

**Source:** [L08](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-08-why-feature-lists-are-harness-primitives/)

Architecture already leaves task lifecycle and issue tracking to clients.

**Verdict:** **client-owned**

Do not add feature_list.json ownership. Expose only a work-item protocol:
behavior/goal, verification refs, current state, dependencies, and evidence refs.

### 17. Completion must be evidence-backed

**Source:** [L09](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-09-why-agents-declare-victory-too-early/)

OutcomeContract distinguishes incomplete, answer-generated, verified, complete,
and failed.

**Verdict:** **covered**

### 18. Prefer deterministic oracles over model self-evaluation

**Source:** [L09](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-09-why-agents-declare-victory-too-early/)

OracleStrength already separates executable/schema/checksum/external observation
from model judgment and VerificationPolicy prefers stronger oracles.

**Verdict:** **covered**

### 19. Maker and checker need separated contexts

**Source:** [L09](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-09-why-agents-declare-victory-too-early/), [L13](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-13-loop-engineering/), [Claude Code](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/claude-code/)

Independent-review templates, judge lane, and subgraphs already support
independent evaluation.

**Verdict:** **strengthen**

Make context separation an explicit acceptance property. Reviewer nodes declare
allowed input refs and must not silently inherit producer transcript/context.

### 20. Verification should span the relevant end-to-end boundary

**Source:** [L10](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-10-why-end-to-end-testing-changes-results/)

Verification is extensible and consequence-aware, but oracle metadata does not
surface unit/component/integration/end-to-end/external scope.

**Verdict:** **strengthen**

Add verification-scope metadata and allow OutcomeContract to require coverage
across named boundaries. High-consequence work may require end-to-end or
external-observation evidence.

### 21. Promote repeated review feedback into enforceable process changes

**Source:** [L10](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-10-why-end-to-end-testing-changes-results/), [L12](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/)

Failure attribution, instruction gotchas, experiments, and lifecycle extensions
provide the pieces.

**Verdict:** **strengthen**

Define a promotion record: observed pattern → hypothesis → experiment →
soft instruction/check → optional hard invariant/extension, with source
provenance and rollback evidence.

### 22. Observability has runtime and process layers

**Source:** [L11](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/)

EventLog covers runtime; graph acceptance, decisions, verification plans/results,
and provenance cover process intent.

**Verdict:** **strengthen**

Explicitly distinguish what happened from why it was allowed/selected/accepted,
but link both under one run/graph/node trace identity instead of separate
ledgers.

### 23. A trace should reconstruct the decision path

**Source:** [L11](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/)

Current requirements still note that harness version is not always on traces.

**Verdict:** **strengthen**

Define a required trace envelope containing harness/config fingerprint,
graph/template version, node, routing decision, context provenance, capability
envelope, verification plan, extension versions, and parent/child lineage.

### 24. Model-visible means replayable

**Source:** [DeepSeek](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/deepseek/)

DeepSeek's strongest invariant is that anything entering a model request can be
reconstructed from append-only session state.

**Verdict:** **gap**

Adopt: **Execution-affecting means observable. Model-visible means replayable.**

Before inference, emit/reference a model-input manifest for messages, context,
tool definitions, instructions, and stable content refs/hashes. Add tests that
reconstruct a recorded call without hidden in-memory state.

### 25. Append-only history should support replay and fork

**Source:** [Claude Code](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/claude-code/), [DeepSeek](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/deepseek/)

EventLog, DecisionLog, checkpoints, and resume already provide foundations.

**Verdict:** **strengthen**

Specify replay versus re-execution semantics and explicit fork lineage from a
stable checkpoint without mutating prior history.

### 26. Clean handoff state is part of "done"

**Source:** [L12](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/)

Completion contracts exist, but no generic post-run clean-state contract
surfaced.

**Verdict:** **gap**

Add an optional ExitContract/CleanStateContract for invariants, unresolved
effects, checkpoint durability, pending-node policy, cleanup hooks, and handoff
record creation. Repository-specific build/test checks are host supplied.

### 27. Cleanup and recovery operations should declare idempotency

**Source:** [L12](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/)

Recovery boundaries and retries exist, but idempotency is not a universal
operation property.

**Verdict:** **strengthen**

Extend operation/effect metadata with idempotency and optional compensation
strategy; retry policy consults it before replaying side effects.

### 28. Goal loops are goal + verifier + stop contract

**Source:** [L13](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-13-loop-engineering/)

Graph goal, OutcomeContract, VerificationPolicy, StopContract, and convergence
already model these pieces.

**Verdict:** **covered**

A small reusable goal-loop graph template could compose the existing pieces;
persistent scheduling remains host-owned.

### 29. Distinguish goal-bounded loops from persistent monitoring loops

**Source:** [L13](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-13-loop-engineering/)

Stop contracts distinguish repeating work and persistent service; wake/schedule
ownership already stays with the client.

**Verdict:** **covered / client-owned**

### 30. Workspace isolation is a capability, not a prompt instruction

**Source:** [L13](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-13-loop-engineering/), [Codex](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/codex/), [P08](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/)

Write scopes and conflict handling protect logical effects but no generic
workspace-isolation provider surfaced.

**Verdict:** **strengthen**

Model workspace/sandbox isolation as a host-provided capability seam. Branches
request isolation without knowing whether the provider uses worktrees,
containers, or a remote sandbox.

### 31. Long loops accumulate verification and comprehension debt

**Source:** [L13](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-13-loop-engineering/)

Budget and cost telemetry cover pieces but no generic loop-health signal exists.

**Verdict:** **strengthen**

Track iterations since independent verification, context growth/compaction
churn, repeated failure class, cost trend, human-review age, and unresolved
assumptions. Policies may wind down or escalate on host thresholds.

### 32. Graphs should expose hidden decision edges

**Source:** [L14](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/), [P08](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/)

ExecutionGraph already stores explicit justified dependency edges with reason
and evidence refs.

**Verdict:** **strengthen**

Linkage should validate all declared execution transitions, not just dependency
existence. Add graph inspection listing possible success/failure/retry/rollback/
escalation transitions before execution.

### 33. Graph-shared state and node-private context are distinct layers

**Source:** [L14](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/)

Payload/evidence/input refs and scoped context providers provide most pieces.

**Verdict:** **strengthen**

Formalize: graph state is durable/shared and may be much larger than inference
context; node context is a private projection; only explicit node exports
re-enter graph-shared state.

### 34. Conditional routing should be first-class and separate from dependencies

**Source:** [L14](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/)

Dependency edges, failure policy, retries, escalation, and routing helpers exist,
but dependency topology is not a complete declarative transition language.

**Verdict:** **strengthen**

Introduce a transition/routing contract for success, predicate branch, retry,
rollback, escalation, cancel, and end. Dependencies answer "what must exist
first"; routing answers "where execution goes next."

### 35. Roll back to the layer that caused the defect

**Source:** [P08](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/)

Failure attribution can identify category/node, but targeted multi-hop rollback
is not surfaced as a first-class graph primitive.

**Verdict:** **gap**

Let verification/failure results carry responsible_node/repair_target and let
routing policy choose the appropriate rollback node, persisting the reason.

### 36. Fan-in needs a named merge/acceptance policy

**Source:** [P08](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/)

fan_out_aggregate and write-conflict handling exist.

**Verdict:** **strengthen**

Promote fan-in policy to a first-class contract supporting ALL, ANY, quorum,
weighted score, deterministic predicate, independent judge, human approval,
and custom injectable strategies.

### 37. Human approval should be a durable node/interrupt

**Source:** [P08](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/), [L14](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/)

Advisor and escalation exist, but no first-class durable human approval
interrupt/wait/resume contract was found.

**Verdict:** **gap**

Add approval request payload, evidence refs, reason, consequence summary,
allowed decisions, timeout, timeout policy, suspended checkpoint, actor
provenance, and resume transition.

### 38. Coordination benefits must beat orchestration cost

**Source:** [L14](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/)

Delegation policy and budgets exist; coordination-cost telemetry is already an
open gap in the requirements map.

**Verdict:** **strengthen**

Feed branch count, duplicated context, fan-in/review cost, expected wall-clock
gain, merge risk, and human-review burden into DelegationPolicy so it can choose
inline/loop/subgraph.

### 39. External anchors prevent mutually reinforcing drift

**Source:** [L14](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/)

Verification already supports external observation, but graphs do not explicitly
identify anchor evidence.

**Verdict:** **strengthen**

Allow outcome/verification contracts to label evidence as an anchor:
real-world outcome, ground-truth dataset, external observation, or human
spot-check. High-autonomy graphs may require periodic anchors.

### 40. Graph metrics/targets need ownership and mutability rules

**Source:** [L14](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/)

Policies and grants exist, but metric ownership/frozen-target semantics are not
first-class.

**Verdict:** **gap**

Add optional graph-state field governance: owner/authority, allowed readers and
writers, mutable/frozen state, and change preconditions. Reuse capability/grant
concepts where possible.

### 41. Capability seams separate interface, provider, and consumer

**Source:** [DeepSeek](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/deepseek/)

DI-first providers, CapabilityEnvelope, registries, strategy adapters, context
providers, and host extension already strongly match this.

**Verdict:** **covered / strengthen**

Make the pattern explicit in architecture docs and apply it to new surfaces
such as workspace isolation, checkpoint storage, human approval transport, and
compaction.

### 42. Expose lifecycle interception around loop/graph execution

**Source:** [DeepSeek](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/deepseek/), [Claude Code](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/claude-code/), [Pi](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/pi/)

LifecycleExtensionRegistry already supports ordered observe/rewrite/block/
replace behavior distinct from telemetry.

**Verdict:** **covered / strengthen**

Finish the existing wrap-mode and scaffolding-migration gaps and publish a
complete lifecycle-boundary inventory so linkage can fail if a required seam is
missing.

### 43. Keep the core small; inject policy

**Source:** [Pi](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/pi/)

DI modularity, open identity, policies, templates, strategies, and lifecycle
extensions already embody this.

**Verdict:** **covered**

Use ablation evidence before adding new core behavior. Prefer provider/policy/
template/extension interfaces over expanding AbstractHarness unless an invariant
is genuinely universal.

### 44. Self-improvement must be evidence-bearing and reversible

**Source:** [Pi](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/pi/)

Harness hypotheses, experiments, template promotion/demotion concepts, and
failure attribution exist.

**Verdict:** **strengthen**

Self-modification should produce a candidate change plus hypothesis, expected
effect, evaluation corpus, rollback plan, and provenance. Never silently mutate
currently executing semantics.

### 45. Separate instruction, procedure, capability, and enforcement layers

**Source:** [Claude Code](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/claude-code/)

Instruction components, providers, tools, capability envelopes, lifecycle
extensions, and policies are already separate.

**Verdict:** **covered / strengthen**

Document the split explicitly. Linkage should warn if a hard capability or
enforcement requirement is supplied only as soft model instruction.

### 46. Send environment deltas instead of repeating full snapshots

**Source:** [Codex](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/codex/)

Environment linkage/probes exist but incremental environment-context projection
is not surfaced.

**Verdict:** **strengthen**

Allow providers to emit versioned snapshots plus deltas with deterministic
reconstruction, reducing repeated context while preserving replayability.

### 47. Child execution isolation covers effects and context

**Source:** [Codex](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/codex/), [Claude Code](https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/claude-code/)

Subgraphs, envelopes, write scopes, context providers, and nested budgets
provide most pieces.

**Verdict:** **strengthen**

Define an IsolationContract covering workspace/effect scope, input context refs,
output export schema, capability envelope, budget share, cancellation/
supersession, and parent-visible summary. This also closes existing child-budget
and cancel/supersede gaps.

### 48. Reusable graph templates need typed I/O contracts

**Source:** [L14](https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/), [P08](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/)

Templates expose soft points, but the existing requirements map already notes
missing I/O contracts for nested subgraphs.

**Verdict:** **strengthen**

Templates/subgraphs declare typed inputs, exported outputs, state/write scopes,
outcome contract, required capabilities, and budget semantics; linkage validates
these before execution.

### 49. Graph descriptions should be inspectable as data

**Source:** [P08](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/)

ExecutionGraph is already serializable data.

**Verdict:** **covered / strengthen**

Add deterministic graph inspection/export for node responsibilities, I/O
contracts, dependencies, transitions, shared-state governance, soft points,
required capabilities, and recovery paths.

### 50. Parallelism must be measured, not assumed beneficial

**Source:** [P08](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/)

Fan-out/aggregate and budget/cost accounting exist.

**Verdict:** **strengthen**

Fan-out traces should report wall-clock critical path, aggregate cost, duplicated
context, fan-in/review cost, coordination failures, and quality delta versus a
matched non-parallel baseline when experimental metadata is available.

## Project/resource validation patterns

The projects mostly operationalize the lecture oracles. Their strongest value
for MechaHarness is how to test the harness itself.

1. [P01](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-01-baseline-vs-minimal-harness/) motivates matched bare-vs-harness experiment fixtures.
2. [P02](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-02-agent-readable-workspace/) motivates fresh-run discovery/linkage tests.
3. [P03](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-03-multi-session-continuity/) motivates crash/resume tests plus resume-cost measurement and rationale preservation.
4. [P04](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-04-incremental-indexing/) reinforces runtime feedback, bounded WIP, scoped context, and stale-context handling.
5. [P05](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-05-grounded-qa-verification/) reinforces independent verification with context isolation.
6. [P06](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-06-runtime-observability-and-debugging/) motivates trace-replay tests.
7. [P07](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-07-loop-engineering-first-loop/) motivates a reference maker/checker goal-loop graph from existing primitives.
8. [P08](https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-08-graph-engineering-first-graph/) is the richest gap test: explicit transitions, fan-in policy, targeted rollback, human approval, and coordination-cost measurement.

The [resource library](https://walkinglabs.github.io/learn-harness-engineering/en/resources/templates/)
is useful as a test corpus for instruction, handoff, evaluator-rubric, and
clean-state concepts. MechaHarness should not copy repository templates as
library policy; translate each into a reusable schema/protocol or leave it
host-owned.

## Recommended priority

### P0 — invariants that fit the existing architecture

1. Model-visible means replayable input/trace manifests.
2. Graph transition/routing contract distinct from dependency edges.
3. Typed template/subgraph I/O and isolation contracts.
4. Explicit node-private context versus durable graph-shared state.
5. Targeted rollback driven by structured failure attribution.
6. Human approval/interrupt with durable suspend/resume.
7. Harness/config/context/extension provenance on every trace.

### P1 — reusable control policies

8. WIP/back-pressure/concurrency policy.
9. First-class fan-in acceptance policy.
10. Clean-state/exit contract.
11. Workspace-isolation capability seam.
12. Staged pluggable context compaction.
13. State-field governance/metric ownership.
14. Anchor evidence requirements.

### P2 — measurement and self-improvement

15. Standard component-ablation experiments.
16. Resume-cost telemetry.
17. Parallel coordination-cost telemetry.
18. Loop-health / verification-debt signals.
19. Harness-health snapshots and evidence-driven retirement.
20. Review-feedback → hypothesis → enforceable-rule promotion records.

## Non-goals / boundaries preserved

This review does **not** recommend moving these into MechaHarness:

- client schedulers or cron/event trigger stores;
- product task/feature databases;
- issue trackers;
- persistent product goals;
- document/knowledge-graph stores;
- concrete June workflows;
- repository-specific AGENTS.md/CLAUDE.md files;
- a mandatory git-worktree implementation;
- a universal WIP=1 rule.

Those belong to clients. MechaHarness should provide contracts and execution
mechanics that make those client choices injectable, verifiable, observable,
replayable, and safe to compose.

## Attribution rule for follow-on requirements

When a requirement or implementation change is derived from this document, keep
the **specific WalkingLabs permalink** in the requirement/user-story footnote,
not merely a link back to this aggregate document.

The desired provenance chain is:

MechaHarness change → this oracle/gap analysis → exact WalkingLabs page →
original sources cited by WalkingLabs.

That keeps later archaeology possible: we can tell not only what changed, but
which external observation motivated it and whether the upstream advice has
since evolved.
