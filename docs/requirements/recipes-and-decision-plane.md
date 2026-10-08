# Reusable graph recipes and typed decision-plane requirements

## Motivation

MechaHarness graphs already provide the primitives for composing deterministic and model-backed execution. A recurring class of agent behavior, however, is smaller than an application graph and larger than a node: a reusable subgraph that implements a well-understood control pattern.

This document names that unit a **recipe**.

The immediate source is rvaniaaaa's 2026 working note, "Move Routine Decisions Off Your Big Model," which argues that high-volume, well-defined decisions should be moved from expensive general models to small structured decision models, while exact computation and final policy remain deterministic code.

Source:
- Original X post / working note: https://x.com/rvaniaaaa/status/2107453108611662172

The note's seven practical rules are:
1. send state as structured data;
2. ask multiple compatible questions in one model call;
3. define the allowed answer levels in advance;
4. keep exact mathematics in code;
5. let code make the final policy decision;
6. use a confidence floor to escalate uncertain decisions;
7. expose only valid actions.

MechaHarness already has architectural overlap with these ideas. The requirement here is not to bolt a second decision framework onto the harness. It is to make these patterns reusable and testable as ordinary graph composition.

A second motivating example is retry. Retry is not merely "run the node again": a useful retry policy may classify a failure, decide whether retry is permitted, select a remediation, apply backoff, constrain attempts, alter context, and eventually escalate. That is naturally a small graph.

## Definition

An **Agentic Recipe** is a reusable, parameterized subgraph that implements a
bounded agent-control pattern and can be embedded in a larger execution graph.

Recipes MUST be composition, not a parallel execution system. A recipe should
compile/instantiate into normal MechaHarness graph primitives and inherit graph
tracing, persistence, resume, testing, policy, and observability.

Recipes are analogous to reusable functions in ordinary programming: named
graph fragments with explicit inputs, outputs, configuration, and contracts.

### Substrate vs concept

The **data structure and factory API remain**
:class:`~mechaharness.graph_templates.base.GraphTemplate` (and related
`GraphTemplateParams`, soft points, registry, provenance stamps). MechaHarness
MUST NOT invent a parallel recipe type system, executor, scheduler, persistence
layer, event bus, or model gateway.

**Agentic Recipe** is the top-level product concept for concrete, useful
templates that encode a readable control pattern. Catalog metadata, docs,
user-story implementation text, and host-facing language SHOULD name recipes
by stable catalog id (for example `verify_repair`, `decision_plane`).

The boundary between a skeletal template and an Agentic Recipe MAY stay soft
until a concrete case forces the call. Prefer promoting when a host would want
to read and reuse the control story as a named unit.

### Human-readable composition (RC-HR)

At the recipe layer, **composition code is a primary readability surface**, not
only documentation. A reader SHOULD be able to open host or library tiling code
and understand how recipes combine into the final graph without reconstructing
the story from opaque node ids or soft-binding dicts alone.

Recipes SHOULD optimize for:

- explicit tiling / embed APIs that read as control flow;
- stable, namespaced node identities that match the source layout;
- soft-point names that describe the human decision being bound;
- hard structure visible in the recipe definition (or an equally readable
  builder), not hidden behind an opaque compiler blob.

### Promotion from requirements and user stories

As part of refining recipes, MechaHarness MUST review current requirements and
user stories, formalize recurring control patterns into concrete recipes where
relevant, and ship those as the first well-documented catalog entries.

Each Agentic Recipe MUST have **at least one user story** that exercises that
recipe as the unit under test (instantiate and run, or statically validate the
tiled graph). Unit tests alone are not enough.

When a story is fulfilled by a recipe, the story `implementation` text MUST
refer to the recipe **by catalog name** so readers learn the recipe vocabulary
alongside modules and Config hooks. Mechanism-only stories (soft points,
stamping, demotion) MAY name `GraphTemplate`; pattern stories MUST name the
recipe.

## Ownership boundary

MechaHarness owns:
- the `GraphTemplate` substrate and recipe composition semantics;
- recipe input/output and configuration contracts;
- deterministic validation and graph linkage;
- reference Agentic Recipes for broadly reusable harness behavior;
- tracing and provenance of recipe expansion/execution;
- test utilities and documentation for recipes;
- the audit→promote process that turns story/requirement patterns into catalog
  recipes.

Applications own:
- domain-specific recipes (still `GraphTemplate` subclasses);
- domain-specific prompts, labels, policies, and thresholds;
- selection of concrete models/providers unless a recipe explicitly accepts a
  router abstraction;
- application-specific side effects;
- readable host tiling that composes library and domain recipes.

A downstream project such as June SHOULD be able to define June-specific recipes
while reusing MechaHarness recipe primitives. A generally useful recipe born in
June SHOULD be extractable back into MechaHarness without changing the recipe
model.

## Requirements

### RC-01: Recipe is a first-class reusable subgraph

MechaHarness MUST provide a first-class way to define a named, versionable, reusable subgraph with:
- typed/validated inputs;
- typed/validated outputs;
- explicit configuration;
- stable internal node identities or deterministic identity derivation;
- declared entry and exit boundaries.

Instantiating the same recipe multiple times in one parent graph MUST NOT create node-ID collisions.

### RC-02: Recipes compile to ordinary graph primitives

Recipe execution MUST NOT require a separate executor.

Instantiation MUST produce or compose ordinary MechaHarness graph nodes/edges so existing graph behavior applies, including:
- validation;
- tracing;
- checkpoint/resume;
- cancellation;
- failure handling;
- model routing;
- tool/capability restrictions.

The parent graph MUST be able to treat the recipe as a logical unit without hiding the internal execution trace.

### RC-03: Recipe linkage is validated before execution

All recipe inputs, outputs, edges, soft-point bindings, required capabilities, and parent-graph connections MUST be resolvable before execution begins.

Invalid composition MUST fail early with actionable diagnostics rather than discovering missing links midway through a run.

This validation MUST work after parameterization, because recipe parameters may determine concrete graph linkage.

### RC-04: Recipe provenance and observability

Every instantiated recipe MUST retain:
- recipe name;
- recipe version or definition fingerprint;
- instance identity;
- parameter/configuration fingerprint;
- mapping between logical recipe nodes and concrete graph node IDs.

Traces SHOULD make it possible to inspect a recipe as one logical span and expand it to its internal nodes.

### RC-05: Recipes are deterministic to instantiate

Given the same recipe definition, version, parameters, and parent binding, graph expansion MUST be deterministic.

Recipe construction MUST NOT itself require model inference.

### RC-06: Recipes support hard structure and soft points

A recipe MUST be able to contain both:
- hard nodes/edges that define the invariant control structure; and
- explicit soft points that a caller may bind or override.

Overrides MUST be constrained by the recipe contract. A caller MUST NOT mutate arbitrary internal structure accidentally.

This permits a reusable MechaHarness recipe to be made concrete by June or another host without forking the recipe.

### RC-07: Substrate is GraphTemplate

Recipe definitions MUST be expressible as `GraphTemplate` (or a thin subclass /
helper layered on it). Hosts register recipes through the existing graph
template registry / Config hook path. Renaming the public vocabulary to
"Agentic Recipe" MUST NOT require a second injectable registry unless a later
ADR proves the split necessary.

### RC-08: Human-readable tiling

Recipe APIs and reference implementations MUST prefer forms a human can read as
structure. Opaque expansion that cannot be inspected as ordinary graph nodes
after instantiate is forbidden. Soft-point and node naming SHOULD be domain-clear
at the leaf (see unambiguous-names rules).

### RC-09: Recipe ↔ user story linkage

Every shipped Agentic Recipe MUST list at least one owning user-story id in its
reference documentation. The owning story's `implementation` field MUST name
the recipe catalog id. Promoting a pattern to a recipe without a story is
incomplete.

## First-wave catalog candidates

Patterns already present as templates or story clusters SHOULD be evaluated for
promotion and documentation as Agentic Recipes (names are catalog ids):

| Catalog id | Existing surface | Anchor story candidates |
|------------|------------------|-------------------------|
| `fan_out_aggregate` | `FanOutAggregateTemplate` | `fangore_graph_template_soft_points`, `fangore_insp_fan_in_policy`, `nubble_insp_coordination_cost` |
| `verify_repair` | `VerifyRepairTemplate` | `fangore_bounded_repair_loop` (loop semantics; dedicated tiling story TBD) |
| `independent_review` | `IndependentReviewTemplate` | `fangore_insp_independent_review` |
| `environment_repair` | `EnvironmentRepairTemplate` | **gap** — needs a story that instantiates this recipe |
| `initialize_preflight` | `InitializePreflightTemplate` | `fangore_insp_initialize_preflight` |
| `decision_plane` | *(new; this document DP-\*)* | new Fangore story; primitives in `fangore_decision_surface_reject` |
| `bounded_retry` | *(new; this document RT-\*)* | new Fangore story; compose with durable resume |

Next-wave patterns with stories but not yet required as recipes:
human approval gates, sparse advisor consult, narrowed delegation envelopes.

## Reference recipe: typed decision plane

MechaHarness SHOULD ship a reference recipe implementing the pattern synthesized in the source working note.

### DP-01: Structured state projection

The decision recipe MUST accept a deliberate projection of harness state rather than implicitly exposing the full graph context.

The projection SHOULD be serializable structured data. Hosts MUST be able to test the projection without invoking a model.

### DP-02: Batched decision questions

The recipe MUST support evaluating multiple compatible bounded questions in one inference call.

Each question MUST define its output domain in advance, such as:
- finite choices;
- boolean/nullable decisions;
- bounded scores;
- another explicitly validated typed result.

The recipe MUST NOT require one model call per question.

### DP-03: Deterministic facts stay outside inference

Exact arithmetic, schema checks, capability existence, counters, deadlines, static graph invariants, and other mechanically knowable facts MUST be computed in deterministic code.

The reference recipe MUST make it natural to feed those facts into a decision call without asking the model to recompute them.

### DP-04: Model output is evidence, not final policy

The decision model MUST return structured signals. Deterministic policy code MUST own the final action when the action can be expressed as deterministic policy over those signals and graph state.

For example, a model may produce classification, risk score, confidence, and recommended executor. Code may then choose route/retry/escalate according to explicit policy.

### DP-05: Valid-action envelope

Every action-like decision question MUST be constrained to actions valid at that decision point.

The model MUST NOT be asked to invent arbitrary commands and have them validated only after generation when the allowed action set can be enumerated beforehand.

The action envelope MAY be derived dynamically from current graph state, capabilities, permissions, or policy, but the derived envelope MUST be explicit in the decision request.

### DP-06: Confidence and escalation

A decision question or batch MUST be able to declare a confidence policy.

When confidence is below the configured floor, output is invalid, questions disagree in a policy-defined way, or the small model otherwise cannot resolve the decision, the recipe MUST expose an escalation path.

Escalation SHOULD be routable rather than hard-coded to "the big model." A host may route to:
- a larger model;
- a specialized evaluator;
- another recipe;
- a human;
- deterministic safe fallback.

### DP-07: Small-model shadow mode

The decision recipe SHOULD support a shadow/evaluation mode in which:
1. the candidate small decision model produces its typed result;
2. the existing production decision path still controls execution;
3. both outcomes are recorded for comparison.

This allows a host to establish empirical suitability before moving a decision off a frontier model.

### DP-08: Decision telemetry is evaluation-ready

Decision traces SHOULD capture enough structured information to evaluate and improve routing:
- question/schema identity;
- state-projection fingerprint;
- selected model/router result;
- typed answers;
- confidence;
- deterministic final policy action;
- escalation reason;
- later outcome/verdict when available;
- latency and usage/cost metadata when available.

Raw sensitive context MUST NOT be required merely to produce aggregate decision metrics.

### DP-09: Model size is policy, not architecture

The recipe MUST NOT encode "small" as a fixed parameter count or provider.

A model qualifies for a decision point because it meets the decision's quality, latency, throughput, cost, and deployment policy. This allows local models, hosted models, and future model classes to use the same recipe.

## Reference recipe: bounded retry

Retry SHOULD be the second reference recipe because it demonstrates that recipes are useful beyond decision-model optimization.

### RT-01: Retry is an explicit subgraph

The retry recipe MUST make attempts, failure classification, remediation, delay/backoff, retry permission, and terminal escalation visible graph behavior rather than hiding all retry semantics inside an executor loop.

### RT-02: Deterministic retry policy where possible

Mechanically identifiable failures and exact attempt/backoff calculations MUST be handled in code.

A model-backed classifier MAY be inserted as a soft point for ambiguous failures.

### RT-03: Bounded attempts and explicit terminal state

A retry recipe MUST require a bounded attempt policy or another explicit termination condition.

Exhaustion MUST lead to a declared terminal/escalation edge. Infinite implicit retry MUST NOT be the default.

### RT-04: Side-effect safety

Retry MUST compose correctly with durable effect identity and recovery semantics.

A retry recipe MUST NOT blindly redispatch an externally visible non-idempotent effect whose acceptance is uncertain. It MUST defer to effect reconciliation before another dispatch is permitted.

### RT-05: Attempt context is deliberate

The recipe MUST allow each attempt to receive:
- prior failure classification;
- attempt number;
- selected remediation;
- relevant prior output/evidence.

It MUST NOT require replaying the entire parent context to every support node.

## Candidate future recipes

The abstraction SHOULD be general enough to express, without special executor features:
- evaluator/judge loops;
- plan -> execute -> verify;
- tool failure recovery;
- model escalation cascades;
- quorum or multi-judge decisions;
- context compression/summarization;
- review-before-mutation;
- speculative candidate generation followed by deterministic filtering;
- human approval gates.

These are examples, not requirements to implement all recipes in the first change.

## Testing requirements

### TEST-01: Static recipe expansion

Tests MUST be able to instantiate and validate recipes without model calls or network access.

### TEST-02: Dependency injection

Reference recipe tests MUST use dependency injection for model runners, clocks, sleepers/backoff, effect adapters, and other external behavior rather than patching global state.

### TEST-03: Decision batching

A test MUST prove that several compatible decision questions can be answered by one injected model invocation and independently validated.

### TEST-04: Invalid decision output

Tests MUST cover invalid enum/score/action outputs and prove they cannot bypass deterministic policy.

### TEST-05: Confidence escalation

Tests MUST prove that below-threshold confidence routes to the configured escalation path and does not silently accept the small-model answer.

### TEST-06: Retry boundaries

Tests MUST cover success on first attempt, success after retry, non-retryable failure, exhaustion, and ambiguous external-effect state.

### TEST-07: Resume inside a recipe

Crash/restart tests MUST exercise checkpoints at multiple locations inside an instantiated recipe and prove that resume preserves recipe identity and does not restart the recipe from its entry unnecessarily.

## Initial implementation scope

A first implementation SHOULD be intentionally small:
1. strengthen `GraphTemplate` composition (namespacing, I/O contracts, provenance)
   without a second type system;
2. deterministic validation and human-readable tiling helpers;
3. recipe provenance in graph/traces (catalog id + instance fingerprint);
4. document and story-link first-wave promotions from existing templates;
5. typed-decision reference recipe (`decision_plane`) with batching,
   valid-action envelopes, and escalation;
6. bounded-retry reference recipe (`bounded_retry`) composing with
   [transactional durable resume](./transactional-durable-resume.md);
7. static/DI tests plus ≥1 user story per shipped recipe;
8. skills/docs that treat Agentic Recipes as a top-level project concept.

Do not create a recipe-specific scheduler, persistence layer, event system, or
model gateway. Reuse MechaHarness primitives.

## Design principle

The harness should spend inference only on uncertainty.

Recipes turn that principle into reusable, **human-readable** graph structure:
deterministic code handles facts and policy, specialized models answer bounded
questions, expensive models receive the genuinely ambiguous remainder, and the
entire control flow remains visible and testable — in traces **and** in the
code that tiles recipes together.
