# Transactional durable graph resume requirements

## Motivation

MechaHarness already serializes `ExecutionGraph` state, restores the latest graph through `GraphStore`, records recovery-boundary vocabulary, and rejects incompatible configuration fingerprints on resume. Those primitives cover graph reconstruction, but they do not yet guarantee durable recovery around externally visible side effects.

A downstream client is the motivating consumer. That client's graph may dispatch a long-running Cursor coding task, lose the MechaHarness process after the remote system accepts that task, and later resume. Replaying the dispatch would create duplicate work. The downstream client should not invent a second graph-recovery protocol to solve this. MechaHarness should provide the reusable persistence and effect-reconciliation primitives, while the downstream client owns its project/task semantics and external adapter.

## Ownership boundary

MechaHarness owns:
- durable checkpoint-store protocols and reference implementations;
- graph/node execution state and recovery boundaries;
- durable effect identity and effect-state transitions;
- resume/reconciliation rules that prevent an already accepted effect from being silently repeated;
- transactional guarantees and crash-recovery acceptance tests.

Downstream clients own:
- project and task identities;
- concrete external systems such as Cursor;
- mapping an external system's run/job handle into the MechaHarness effect contract;
- application-specific polling, completion criteria, and business semantics.

The design MUST remain backend-neutral at the protocol layer. SQLite is the required local reference backend, not a requirement that all hosts use SQLite.

## Requirements

### DR-01: CheckpointStore is the executor persistence seam

`GraphExecutor` MUST depend on the `CheckpointStore` abstraction rather than constructing `GraphStore` directly as its authoritative persistence mechanism.

The store MUST support at least:
- saving a graph checkpoint for a `run_id`;
- loading the latest valid checkpoint;
- reading the persisted configuration fingerprint;
- reading the persisted recovery boundary;
- monotonically ordered checkpoint revisions.

The existing EventLog adapter MAY remain available for compatibility/observability, but an event stream MUST NOT be the only persistence option.

### DR-02: Durable SQLite reference backend

MechaHarness MUST provide a SQLite-backed checkpoint implementation suitable for a single-host durable runtime.

It MUST:
- survive process termination and restart;
- use transactions for checkpoint/recovery metadata updates;
- isolate runs by `run_id`;
- retain enough revision history to diagnose and test recovery;
- initialize/migrate its own schema deterministically;
- support concurrent readers and serialize conflicting writes safely.

A host SHOULD be able to use one database for many runs. A separate database file per session MUST NOT be required.

### DR-03: Explicit external-effect identity

A graph node that can create an externally visible side effect MUST be able to associate the attempt with a stable `effect_id`.

The persisted effect record MUST be able to represent:
- `run_id`;
- `node_id`;
- node attempt;
- `effect_id`;
- backend/provider identity;
- external run/job handle when known;
- effect state;
- timestamps/revisions sufficient for recovery diagnostics.

The effect contract MUST be generic. `Cursor` is an example backend, not a core MechaHarness type.

### DR-04: Durable intent before external dispatch

Before an effectful runner performs a non-idempotent external dispatch, MechaHarness MUST durably record the intent/effect identity.

The intent record MUST commit before the external call is made.

This creates a recoverable distinction between:
1. no dispatch was intended;
2. dispatch was intended but acceptance is unknown;
3. the external system accepted the dispatch;
4. the effect completed or failed.

### DR-05: Record external acceptance

After an external system accepts a dispatch, its external handle MUST be durably associated with the pre-existing `effect_id` before the node can be considered safely checkpointed past dispatch.

For a downstream client, an example is a Cursor run identifier. The core contract MUST not assume Cursor.

### DR-06: Resume reconciles uncertain effects instead of redispatching

On resume, an effect record in an uncertain or accepted state MUST NOT cause blind re-execution of the dispatch.

The planned Agentic Recipe `bounded_retry` (see
[Recipes and decision plane](./recipes-and-decision-plane.md) RT-04) MUST compose
with this reconciliation path rather than reimplementing effect identity.

The executor MUST expose a reconciliation path that allows the host adapter to determine whether the external effect:
- was never accepted and may be dispatched;
- exists and should be observed/resumed;
- completed and can be reduced into the graph;
- failed and should enter normal failure policy;
- cannot be determined and therefore requires an explicit recovery/escalation decision.

Unknown MUST NOT silently mean "dispatch again."

### DR-07: Recovery boundaries have executable semantics

The existing recovery boundaries (`planning`, `dispatch`, `post_effect_pre_record`, `reduce`, `commit`) MUST have documented executor semantics rather than being metadata only.

In particular, tests MUST cover a crash after external acceptance but before graph-result recording. Resume MUST recover/reconcile the existing effect without creating a second external dispatch.

If implementation experience shows the current boundary names are insufficient, they MAY be revised, but the observable crash guarantees MUST remain.

### DR-08: EventLog remains observational

Lifecycle and graph events SHOULD continue to describe execution for debugging, telemetry, and audit.

Correct recovery MUST NOT depend on every observational event having been flushed. Authoritative checkpoint/effect state MUST be recoverable from the durable persistence contract.

An implementation MAY store events in the same SQLite database, but checkpoint/effect correctness MUST not depend on replaying the event stream.

### DR-09: Fingerprint safety remains enforced

Durable resume MUST retain the existing incompatible-fingerprint refusal behavior.

The persisted fingerprint and checkpoint/effect state MUST be read consistently enough that resume cannot accidentally reconcile an external effect under incompatible graph semantics.

### DR-10: Crash-window acceptance matrix

Automated acceptance tests MUST kill or simulate failure at minimum at these boundaries:
1. before durable dispatch intent;
2. after intent commit but before external call;
3. after external acceptance but before acceptance handle is recorded;
4. after acceptance handle is recorded but before node outcome is reduced;
5. after node outcome is reduced but before the next graph checkpoint;
6. after final commit.

For each case, the test MUST assert both graph outcome and number of external dispatches. A recoverable run MUST never produce a duplicate dispatch solely because the MechaHarness process restarted.

### DR-11: Existing non-effectful runners remain simple

Pure/idempotent graph runners MUST NOT be forced to implement external-effect reconciliation.

The effect protocol SHOULD be opt-in through a runner capability/interface or equivalent injectable abstraction so existing computation nodes retain the current lightweight execution path.

### DR-12: Static-data crash-injection user story

Add a first-class static-data user story that rigorously exercises durable resume with a dependency-injected fake external coding-job backend shaped like a downstream client's intended Cursor integration.

The story MUST run as a parameterized crash-location matrix. Each case starts from the same deterministic fixture, injects a process-failure/crash at exactly one execution boundary, constructs a fresh executor against the same durable SQLite store, resumes the run, and verifies the recovered result.

At minimum inject crashes:

1. before durable dispatch intent;
2. immediately after dispatch-intent commit but before the external call;
3. immediately after the fake backend accepts the job but before its external handle is durably recorded;
4. immediately after the external handle is recorded but before node outcome/reduction;
5. immediately after reduction but before the next graph checkpoint;
6. during/after final commit, including restart after terminal state is durable.

For every crash location, the fixture MUST assert:

- final graph/node state;
- persisted recovery boundary and revision;
- effect state before and after restart;
- whether reconciliation was invoked;
- the exact number of calls to external dispatch;
- the exact external job identity observed after restart;
- whether the node runner itself was re-entered;
- emitted failure/recovery diagnostics;
- that a completed/accepted external effect is never duplicated solely because the process crashed.

The fake backend MUST expose deterministic counters and stable job handles through dependency injection so these assertions require no timing assumptions, network access, or real Cursor service.

The particularly important regression case is:

```text
persist dispatch intent
        |
        v
fake backend accepts external job   (dispatch_count = 1)
        |
        X  injected crash before checkpoint/result record
        |
        v
fresh GraphExecutor + same SQLite store
        |
        v
reconcile existing effect/job
        |
        v
complete graph                       (dispatch_count MUST still = 1)
```

The test MUST fail if resume reaches the dispatch adapter a second time for an effect already known or recoverable as accepted.

Where acceptance after the external call is genuinely unknowable, the story MUST exercise the explicit uncertain-effect path rather than assuming either success or failure. The expected result may be reconciliation or a needs-attention/escalation state, but MUST NOT be an automatic duplicate dispatch.

The story SHOULD be implemented in the repository's normal static fixture/story mechanism so it participates in the same deterministic acceptance suite as the existing durable-resume stories. It MAY use multiple fixture variants if that keeps each expected result legible.

The story MUST demonstrate the ownership boundary: downstream-client-like code supplies backend-specific reconciliation while MechaHarness supplies durable state, effect identity, crash injection, and resume control.

## Compatibility and migration

Existing in-memory/EventLog-backed execution SHOULD continue to work for ephemeral/test workloads. Durable semantics MUST be explicit: a host that has not configured durable persistence MUST NOT be led to believe it has process-restart durability.

The public API SHOULD make the difference between ephemeral checkpointing and durable checkpointing inspectable/documented.

## Definition of done

This requirement is complete when:
- `GraphExecutor` uses an injectable checkpoint persistence seam;
- a SQLite reference store passes restart tests;
- effect intent/acceptance state is persisted transactionally;
- uncertain effects reconcile rather than automatically redispatch;
- the crash-window matrix passes with exactly one external dispatch where the first dispatch was accepted;
- fingerprint incompatibility still refuses resume;
- a downstream-client-shaped external coding-job story passes without adding client-specific policy to MechaHarness core.
