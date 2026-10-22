# Inspiration: Inversion-of-Control Execution via Durable Graph Generators

Date: 2026-10-19
Status: Proposed design and requirements, not an implemented API
Project: MechaHarness
Related use cases: Finder of Lost Keys photorealistic production; NeoStudio virtual production; local Qwen3 32B workers directed by frontier-model sessions

## Motivation

A frontier agent (Cursor, Codex, ChatGPT or another MCP-capable client) should be able to launch a MechaHarness graph and let inexpensive local inference and deterministic tools perform the token-heavy work. When the graph requires higher-level judgment, it should **yield a structured guidance request as the result of the tool call**. The same frontier-agent conversation then interprets the request and calls the tool again with guidance. The graph resumes from its durable checkpoint.

This is inversion of control at the *execution* boundary, **not** pyiv dependency injection, model-to-model callbacks, or a requirement for the local worker to call a frontier model API. The initiating intelligence is simultaneously the driver and a source of direction, without requiring recursive reentry into an outstanding MCP tool call.

A graph needing no guidance may complete in its initial invocation. A complex graph may yield multiple ordered statuses, each consumed in the same driving session.

## Core mental model

A graph run is a **durable, externally driven generator**:

- `start(recipe, inputs)` creates and advances a run to a meaningful yield.
- `resume(run_id, response?, expected_sequence)` consumes an optional response to the pending yield and advances to the next yield.
- `inspect(run_id)` exposes diagnostics, checkpoints, pending requests and artifact references without advancing.
- `cancel(run_id)` terminates or requests safe cancellation.
- `list_recipes()` exposes discoverable recipe names and typed input schemas.

Conceptual pseudocode (not a commitment to Python stack serialization):

```python
status = await driver.start("folk.performance", inputs)
while status.kind not in {"completed", "failed", "cancelled"}:
    if status.kind == "advice_requested":
        answer = await driver.obtain_guidance(status)
        status = await driver.resume(status.run_id, answer, status.sequence)
    else:
        status = await driver.resume(status.run_id, expected_sequence=status.sequence)
```

A graph's node may conceptually `await context.request_guidance(...)`, but the runtime implements it through an explicit persisted suspension/continuation boundary, not by attempting to serialize a live coroutine stack.

## Architecture and ownership

1. **MechaHarness core:** graph state machine, yield/advice primitives, continuation semantics, durable checkpoints, execution log, dependency invalidation and authorization hooks.
2. **Protocol/driver contract:** transport-neutral typed operations and event envelopes. It must not depend on MCP, curses or a model SDK.
3. **MCP stdio adapter:** a piped MCP server exposing the same contract as tools to Cursor/Codex and other MCP clients. Stdio must keep protocol output on stdout and diagnostics on stderr; no human prompts on the MCP transport.
4. **Human CLI and TUI:** clients of the same MCP tools, rendering progress, choices, evidence and free-form guidance. A noninteractive plain-text mode is required; curses is optional presentation.
5. **Scripted test driver:** deterministic, first-class client of the same MCP protocol. MechaHarness unit tests may exercise the transport-neutral core directly; MCP integration tests exercise the real stdio adapter.
6. **Local worker backends:** Qwen3 32B, other specialist models, media backends and deterministic nodes perform work within graph-defined budgets.

The core must not assume the driver is intelligent. Guidance can be a typed selection, structured parameters, a free-form explanation, deferral, or a refusal. Approval is separate from advisory guidance.

## Yield protocol

Each externally visible yield is an ordered, immutable envelope:

```json
{
  "run_id": "folk-scene-072",
  "sequence": 3,
  "kind": "advice_requested",
  "checkpoint_id": "cp-003",
  "request_id": "req-003",
  "payload": {
    "question": "How should exhaustion affect the sword maneuver?",
    "choices": [
      {"id": "slow", "label": "Slower, imperfect technique"},
      {"id": "precise", "label": "Precise maneuver followed by collapse"}
    ],
    "recommendation": "precise",
    "evidence_refs": ["artifact://folk-scene-072/performance-analysis"],
    "requested_authority": "artistic_direction",
    "context_version": "scene-072@v4"
  }
}
```

Kinds: `progress` (optional), `advice_requested`, `running` (nonblocking or timeout), `completed`, `failed`, `cancelled`. `running` must not be interpreted as a demand for model reasoning; the client can wait/poll. The protocol should permit completion on the first `start` call and should not generate token-expensive progress chatter by default.

`resume` supplies `run_id`, expected `sequence`, pending `request_id` when applicable, guidance and an idempotency key. Guidance must be rejected if stale, unauthorized, mismatched to the pending request, or incompatible with its schema. A repeated identical call returns the previously committed result; a conflicting repeat fails safely.

Use structured output for machine interpretation and compact, readable summaries for agents and humans. Large logs, media and evidence remain in referenced artifacts accessible via `inspect` rather than being copied into every yield.

## Execution state machine

```text
CREATED -> RUNNING -> COMPLETED
               |  \-> FAILED
               |  \-> CANCELLED
               |  \-> RUNNING (nonblocking status)
               \-> GUIDANCE_REQUIRED --(authorized resume)--> RUNNING
                          \-> SUSPENDED / deferred
```

Only committed yield points are externally observable. The implementation must define transaction boundaries between side effects, event logging, checkpoint persistence and yield publication. Use durable run IDs and explicit continuation records. Process restarts must not lose pending questions or silently rerun already committed side effects. For nontransactional external tools, use idempotency tokens or reconciliation records; do not promise exactly-once effects where a backend cannot provide them.

## Driver independence and session continuity

- Frontier agent: calls MCP tools from its **existing session**, retaining strategic context and its previous advice. MechaHarness does not receive or store the entire conversation by default.
- Human operator: CLI or curses TUI receives the same typed question, inspects evidence and submits a response or defers.
- Scripted test: consumes the same yield sequence and supplies fixture responses, asserting exact request semantics and resulting artifacts.
- Local agent: may also drive the graph through the same contract.
- Authorized takeover: a new driver can recover a suspended run after an explicit ownership transfer. The run belongs to MechaHarness, not the original MCP subprocess or model conversation.

MCP clients do not inherently allow reentering a model session during a pending tool call. The design deliberately returns guidance requests as ordinary tool results and waits for the caller's next tool invocation.

A stdio MCP process may be short-lived or disconnected; durable graph state must live outside that process when recovery across sessions is required.

## Controller ownership, authorization and safety

Associate each run with a controller identity or lease and scope allowed operations. Separate:
- advisory recommendation,
- direction within delegated constraints,
- proposed requirement change,
- final approval reserved for an authorized actor.

Changing approved production assets or requirements must not be possible through an ordinary advice response unless explicitly authorized. Inspect-only clients must not race the controlling driver. Support lease expiry and deliberate transfer; never infer that possession of a run ID alone confers control.

## Cost and escalation policy

Graph contracts define local worker budgets, retry ceilings, evidence thresholds and which questions merit external guidance. Local inference should handle retrieval, drafting, revision, validation preparation and routine retries. Deterministic checks and independent evaluators should gate successful work, rather than a worker simply asserting confidence.

Batch related guidance questions where their dependencies permit, but preserve question identity and order. Track local tokens, frontier advice frequency, latency, retry rates, cost estimates and acceptance outcomes. Optimize for verified useful work per frontier intervention, not just fewest tokens.

## Testability and regression replay

Provide a first-class `ScriptedDriver` supporting expected-yield assertions, typed response fixtures, strict unexpected-advice failure, and recording/replay. Fixtures should match semantic request identity and context version, not merely ordinal position.

Required test scenarios:

1. Trivial graph completes in `start`, with no extra calls.
2. Local-only graph completes with zero guidance requests.
3. Graph yields advice, receives typed guidance, resumes, and completes.
4. A human CLI client and a scripted driver execute the same recipe without changes.
5. Real stdio MCP transport is exercised in an integration test, including clean stdout framing.
6. A suspended graph survives server/executor restart and returns the identical pending question.
7. Crash injection before/after checkpoint persistence and external side effects verifies recovery behavior.
8. Duplicate resume with the same idempotency key is harmless; stale/conflicting responses are rejected.
9. A driver disconnects; an authorized new driver inspects and resumes the run.
10. Unexpected guidance requests fail strict regression fixtures.
11. Guidance/approval authority is enforced and cannot silently overwrite locked artifacts.
12. Multiple parallel local workers can yield related questions without nondeterministic application of advice.
13. Test doubles use dependency injection rather than process-global monkeypatching, with explicit fake inference/tool backends.

Include offline unit/contract tests and optional live end-to-end tests against a local model and MCP client.

## Suggested milestones

**M0: Inventory existing MechaHarness primitives.** Map current graph context, event log, resumability, checkpoints, hard/soft nodes, model routing and any existing MCP integration. Reuse instead of replacing. Record compatibility decisions.

**M1: Core durable yield.** Implement typed `GuidanceRequest` and `GraphYield`, explicit suspension/resume and scripted in-process tests. Start with one sequential graph.

**M2: Stdio MCP transport.** Expose start/resume/inspect/cancel/list recipes. Test actual piped client/server behavior and timeout handling.

**M3: Scripted driver and replay.** Strict fixtures, event recording, semantic replay and crash-location tests.

**M4: Human drivers.** Plain-text CLI first, curses/TUI second; both exercise MCP rather than private runtime internals.

**M5: Parallel execution and ownership transfer.** Related advisory batching, leases, controlled handoff and concurrency stress tests.

**M6: Production pilot.** FOLK character or performance workflow using local Qwen and deterministic QA, with a frontier agent advising only on ambiguous artistic decisions. Compare quality, costs and latency to an all-frontier baseline.

## Candidate requirements

- **R-IOC-GENERATOR:** Graph runs expose a transport-neutral durable generator contract with ordered yields.
- **R-IOC-GUIDANCE:** Nodes can request typed external guidance through explicit persisted continuation points.
- **R-IOC-SESSION:** Frontier guidance returns through ordinary MCP tool responses and subsequent calls in the same caller session; no recursive callback requirement.
- **R-IOC-MCP:** Provide a piped stdio MCP server mapping tools to core graph operations without embedding core semantics in transport.
- **R-IOC-DRIVERS:** Agent, human CLI/TUI and deterministic test drivers use the same tool protocol and graph definitions.
- **R-IOC-REPLAY:** Record and replay advisory decisions against semantic request identities, with strict regression mode.
- **R-IOC-RESUME:** Suspension and pending advice survive crashes and MCP process restarts.
- **R-IOC-IDEMPOTENT:** Resume uses sequence checks and idempotency semantics; external side effects have documented recovery guarantees.
- **R-IOC-AUTH:** Controller ownership and advisory-versus-approval authority are explicit and enforceable.
- **R-IOC-BUDGET:** Graphs measure local work, guidance frequency, retries, latency and cost.
- **R-IOC-OFFLINE:** Contract, recovery and driver tests can run without live models or media backends.

## Open questions

- [ ] Which existing MechaHarness resumability primitives can represent a pending guidance continuation?
- [ ] Should the core expose `advance` as distinct from `resume`, or unify them?
- [ ] How should nonblocking `running` and wait/poll behave across clients with differing tool timeouts?
- [ ] What is the minimum viable stable schema for typed guidance, evidence and requested authority?
- [ ] How are controller credentials/leases handled for a local stdio MCP server and cross-session takeover?
- [ ] How should multiple advisory requests from parallel branches be grouped and ordered?
- [ ] What event storage and side-effect reconciliation guarantees exist today?
- [ ] How are fixtures generated from recorded runs without leaking confidential frontier-session context?
- [ ] Which existing graph recipes make the best initial offline and live tests?

## Design constraint

**Do not build a second harness around MCP or a new dependency injection framework.** The generator is a new MechaHarness execution construct. MCP is one adapter, and curses, plain-text and test drivers are clients of the same contract. Production-specific artistic semantics remain with FOLK or NeoStudio.

## Related

- Normative: [Durable graph generators](../requirements/durable-graph-generators.md)
- Story map: [durable-graph-generators-requirements-map.md](./durable-graph-generators-requirements-map.md)
- Orthogonal: [Self-revising recipe evolution](./self-revising-recipe-evolution.md) — which recipe is active vs how a run is driven
