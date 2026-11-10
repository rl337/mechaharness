# Durable graph generators (driven execution)

Normative library requirements for **durable graph-generator inversion of
control**: the primary host-facing execution model for long-running,
judgment-bearing graphs.

Inspiration provenance (non-normative):
[Durable graph generators inversion of control](../inspiration/durable-graph-generators-inversion-of-control.md).
Story map:
[durable-graph-generators-requirements-map.md](../inspiration/durable-graph-generators-requirements-map.md).

## Thesis

A frontier agent, human operator, or scripted test **drives** a MechaHarness
run through ordered yields. Inexpensive local inference and deterministic tools
perform token-heavy work. When the graph needs higher-level judgment, the run
**yields** a structured guidance request as the result of the driver call. The
same driver session interprets the request and calls again with guidance. The
graph resumes from its durable checkpoint.

This is inversion of control at the *execution* boundary — not pyiv dependency
injection, not model-to-model callbacks, and not a requirement for the local
worker to call a frontier model API.

## Non-goals

- Do **not** build a second harness or graph engine around MCP.
- Do **not** serialize live coroutine stacks; use explicit persisted
  suspension/continuation records.
- Do **not** collapse advisory guidance into human approval
  (`ApprovalInterrupt`) or in-process sparse advisor consults (`Advisor`).
- Video production / studio host artistic semantics stay in host apps.

## Requirements

### DG-01: Transport-neutral durable generator contract

MechaHarness MUST expose a transport-neutral API with at least:

- `start(recipe_id, inputs, *, controller_id) → GraphYield`
- `resume(run_id, response?, *, expected_sequence, …) → GraphYield`
- `inspect(run_id) → RunInspection`
- `cancel(run_id, …) → GraphYield`
- `list_recipes() → list[RecipeDescriptor]`

Wire form: `mechaharness.durable_graph_generator.DurableGraphGenerator`.
Host ergonomics: `host_kit.host_durable_graph_generator`, `durable_generator_host`.

`recipe_id` MUST resolve through `GraphTemplateRegistry` (registered recipes
only). Free-form executable graph synthesis is out of scope for this contract.

### DG-02: Ordered immutable yields

Each externally visible yield MUST be an ordered, immutable envelope
(`GraphYield`) carrying at least `run_id`, `sequence`, `kind`, and optional
`request_id` / `checkpoint_id` / `recipe_id` / `graph_id`.

Kinds MUST include `advice_requested`, `completed`, `failed`, `cancelled`, and
MAY include `progress` (off by default) and `running` (poll/wait — not a demand
for model reasoning).

### DG-03: Typed guidance continuation

Nodes / soft points MAY request typed external guidance
(`GuidanceRequest` / soft point kind `guidance` / node component
`guidance_request`). The runtime MUST persist the pending request and resume
only through an authorized `resume` that matches `request_id` and schema.

Ordinary guidance MUST NOT satisfy `requested_authority=final_approval`; that
path remains `ApprovalInterrupt`.

### DG-04: Driver-session resume (no recursive callback)

Guidance MUST be returnable as an ordinary call/tool result. Completing the
guidance MUST NOT require reentering a model session during a pending MCP tool
call. A subsequent `resume` in the same driving session is the required path.

### DG-05: MCP is an adapter

A piped stdio MCP server MAY map tools to DG-01 ops. Core MUST NOT depend on
MCP, curses, or a model SDK. Stdio adapters MUST keep protocol on stdout and
diagnostics on stderr.

### DG-06: Shared driver contract

Agent, human CLI/TUI, and `ScriptedDriver` MUST use the same core ops and
recipe definitions. Presentation differs; graph semantics must not.

### DG-07: Scripted replay and offline tests

MechaHarness MUST ship `ScriptedDriver` supporting expected-yield assertions,
typed response fixtures, and strict unexpected-advice failure. Contract,
recovery, and driver tests MUST run without live models or media backends.

### DG-08: Survive restart

Pending guidance and run phase MUST survive process restart when a durable
`GeneratorRunStore` / `CheckpointStore` is bound. Rehydrate MUST present the
identical pending `request_id` and question. Guidance suspension MUST compose
with [transactional durable resume](./transactional-durable-resume.md) rather
than inventing a second recovery protocol.

### DG-09: Sequence and idempotency

`resume` MUST enforce `expected_sequence`. An identical idempotency key MUST
return the previously committed yield; a conflicting repeat MUST fail safely.
External side effects keep the recovery guarantees of the durable-resume
requirements.

### DG-10: Controller ownership

Each run MUST associate a controller identity. Possession of `run_id` alone
MUST NOT confer control. Inspect-only clients MUST NOT race the controlling
driver for mutating ops. Lease transfer MAY be added later; M1 requires
rejecting foreign controllers on resume/cancel.

### DG-11: Cost and guidance frequency

Runs MUST expose counters for local steps, guidance yields, resumes, and
rejected resumes (`inspect().cost`) so hosts can optimize verified useful work
per frontier intervention.

### DG-12: Events and node components

Yield publish, guidance resume, and cancel MUST emit warehouse-joinable
`core:*` events with `run_id`, `graph_id`, `recipe_id`, and sequence /
`request_id` when applicable. Guidance soft points MUST project
`guidance_request` node components (kinds ⊆ real surfaces).

### DG-13: Relationship to GraphExecutor

`GraphExecutor` remains the internal node walker. The generator drives
execution to the next committed yield; it MUST NOT replace the walker with a
parallel graph engine.

## Milestones

| Milestone | Scope |
|-----------|--------|
| M1 | In-process generator, ScriptedDriver, stories, docs/API (this change) |
| M2 | Stdio MCP adapter |
| M3 | Recording/replay polish and crash-location matrix expansion |
| M4 | Human plain-text CLI (curses optional) |
| M5 | Parallel advisory batching, leases, ownership transfer |
| M6 | Host production pilots (video production / studio apps) |

## Definition of done (M1)

- `DurableGraphGenerator` + `ScriptedDriver` exported and Config-bound
- Persona stories for DG-01..11 (MCP/CLI as explicit gap stories)
- Architecture and reference docs describe the generator as a primary pillar
- Unit + story acceptance green offline
