# Architecture

MechaHarness is built on four founding principles — **DI modularity**,
**native multi-model / lanes**, **cost in the object model**, and **built-in
EventLog telemetry** — described on the [docs home](./index.md). This page is
the structural map: provider I/O and agent-loop policy stay separate extension
axes. Wiring is **pyiv dependency injection first**. OpenAPI (`RunRequest` /
`run()`) is the non-DI facade, not a second architecture. See
`.cursor/rules/di-first.mdc`.

For long-running, judgment-bearing graphs, the **durable graph generator** is
the primary host-facing execution model: external drivers advance durable runs
through ordered yields. One-shot harness loops remain for short work. See
[Durable graph generators](./requirements/durable-graph-generators.md).

```text
 Frontier / human / ScriptedDriver
              │
              ▼
   DurableGraphGenerator          ← primary long-run façade
   start / resume / inspect / …
              │
              ▼
        GraphExecutor + CheckpointStore   ← internal walker + durability
              │
              ▼
        GraphTemplateRegistry (Agentic Recipes)

 Short path (unchanged):
┌─────────────┐     ┌─────────────┐
│  CLI (Typer)│     │ API (FastAPI)│
└──────┬──────┘     └──────┬──────┘
       │                   │
       └─────────┬─────────┘
                 ▼
          RunRequest / run()     ← OpenAPI non-DI contract
                 │
                 ▼
        ┌────────────────┐
        │ MechaHarnessConfig │  ← pyiv Config (template-method hooks)
        │  SettingsConfig    │
        └────────┬───────┘
                 │ get_injector
                 ▼
        ┌────────────────┐
        │ AbstractHarness │  ← class hierarchy / template method
        │  pass_through   │
        │  tool_loop      │
        │  react          │
        │  openai_tools   │
        │  anthropic_tools│
        └────────┬───────┘
                 │ uses
                 ▼
        ┌────────────────────┐
        │ InferenceStrategy  │  ← strategy pattern
        │  openai_compat     │     (openai, lmstudio, vllm, ollama)
        │  anthropic         │
        │  mock              │
        └────────────────────┘
```

## Dependency injection

**Pattern:** Template-method pyiv `Config` + constructor injection (pyiv ≥ 1.1)  
**Code:** `mechaharness.di`

Hosts **must** subclass `MechaHarnessConfig` (or use `run()`). Hand-constructing
harness families is unsupported. `configure()` class-binds `InferenceStrategy`
and `AbstractHarness` (singleton), aliases `Completer` to the strategy, and
registers `Settings`, `HarnessConfig`, `ToolRegistry`, `EventLog`,
`AccessControl`, `CostAccountant`, `InferenceEnvironment`,
`APIConnectionConfig` (judge), `JudgeProvider`, `GraphNodeRunnerRegistry`,
`GraphFailurePolicy`, `GraphEscalation`, `OperationRegistry`,
`LinkageResolver`, `VerificationPolicy`, `DelegationPolicy`, `Advisor`,
`AdvisorPolicy`, `GraphTemplateRegistry`, `ContextProviderRegistry`,
`CapabilityEnvelope`, `LifecycleExtensionRegistry`, `GraphExecutor`,
`DurableGraphGenerator`, `GeneratorRunStore`, and `GeneratorControllerAuth`.
Subclasses override `get_inference_class()` and `get_harness_class()` (called
from the Config constructor). Override `get_access_policy()` (or
`get_grants()`) for deny-by-default tool grants; compose reusable sets with
`CompoundPolicy`. Override `include_subagent_tools()` to set
`HarnessConfig.subagent_tools` (parent EventLog query tools). Override
`get_inference_environment()` for host profile probes.
Override `get_judge_connection()` / `get_judge_provider()` for judge wiring and
wire adapters. Override `get_node_runner_registry()` /
`get_graph_failure_policy()` / `get_graph_escalation()` /
`get_linkage_resolver()` / `get_graph_template_registry()` /
`get_lifecycle_extension_registry()` /
`get_durable_graph_generator()` / `get_generator_run_store()` /
`get_generator_controller_auth()` for plan execution, lifecycle mods, and
driven durable runs.

**Config ownership:** lane- and provider-specific knobs belong on the owning
injectable (e.g. `SimpleHttpConnectionConfig.from_env` for `MECHA_JUDGE_*`), not
as a growing pile of fields on `Settings`. Providers are never attributes of
`Settings`. Shared edges bind in `configure()` and are consumed by constructor
injection / `inject(T)` — not via `getattr` lazy caches on Config or sibling
`get_*` calls that pull collaborators. See `.cursor/rules/di-first.mdc`,
`docs/requirements/dependency-injection.md`, and the `di-config-ownership`
skill.

`SettingsConfig` implements the hooks via overridable `inference_classes()` /
`harness_classes()` maps plus `Settings.inference_backend` /
`Settings.harness_family`. That is the configuration path for CLI/HTTP callers
who pick backends by name.

(durable-graph-generator)=
## Durable graph generator (driven execution)

**Pattern:** Externally driven durable generator over registered recipes  
**Code:** `mechaharness.durable_graph_generator`, `mechaharness.durable_generator_host`, `mechaharness.host_kit`  
**Requirements:** [Durable graph generators](./requirements/durable-graph-generators.md)  
**Reference:** [Durable graph generators](./reference/durable-graph-generators.md)

Hosts (frontier MCP clients, human CLI/TUI, `ScriptedDriver`) call
`start` / `resume` / `inspect` / `cancel` / `list_recipes`. The generator
emits ordered `GraphYield` envelopes; `advice_requested` returns as an ordinary
call result so the driver session can answer without recursive reentry into a
pending MCP tool call. Continuation state lives in `GeneratorRunStore` and
composes with `CheckpointStore`. Advisory guidance is distinct from
`ApprovalInterrupt` and from in-process `Advisor` consults. MCP is a planned
stdio adapter of the same contract — not a second harness.

Prefer this façade when a run may yield guidance, outlive a process, or be
driven from an external conversation. Recipe evolution
([self-revising inspiration](./inspiration/self-revising-recipe-evolution.md))
selects *which* registered recipe is active; the generator drives *how* that
run advances.

(execution-graph)=
## Execution graph

**Pattern:** Injectable scheduler over durable DAG primitives  
**Code:** `mechaharness.graph`, `mechaharness.graph_executor`

`ExecutionGraph` / `GraphStore` model nodes, justified edges, checkpoints, and
verification helpers. `GraphExecutor` depends on an injectable
`CheckpointStore` (ephemeral `EventLogCheckpointStore` by default; durable
`SqliteCheckpointStore` for process-restart recovery). The durable generator
**drives** this walker to the next committed yield; it does not replace it.
`GraphExecutor` walks ready nodes:
it requires `core:graph.execute` and a `BudgetPolicy` on every `run()`,
dispatches open `kind` strings through a host-populated
`GraphNodeRunnerRegistry`, charges a shared `Budget` (soft wind-down / hard
fail; nested subgraphs aggregate), applies `GraphFailurePolicy`
(retry / escalate / fail), optional `GraphEscalation` (needs
`core:graph.escalate`), and emits `core:graph_start` / `core:graph_end` plus
per-node events. Effectful nodes opt into `EffectfulGraphNodeRunner` for
durable intent/acceptance and resume reconciliation. Bind via Config hooks
`get_node_runner_registry()`, `get_graph_failure_policy()`,
`get_graph_escalation()`, `get_checkpoint_store()`, and
`get_graph_executor_class()` — not Settings.

Do not add string registries or a global injector. Domain types stay pyiv-free.

**Lanes vs flavors:** `InferenceEnvironment` lanes (`reason` / `judge` /
`media`) are capability partitions. Same-lane Completer / JudgeProvider
**flavors** are extra pyiv `Named` bindings from
`MechaHarnessConfig.completer_bindings()` /
`judge_bindings()`; host constructors select them with
`Annotated[T, Named(...)]` / `Matched(...)` (pyiv ≥ 1.1). See
[Dependency injection](./guides/dependency-injection.md).

Before substantive work, `GraphExecutor` runs an injectable
`LinkageResolver` (runner kinds, grants, operation binds, stop contracts,
envelopes, environment). Checkpoints carry a config/graph fingerprint so
resume refuses incompatible changes.

(agentic-recipes)=
### Agentic Recipes

**Pattern:** Parameterized subgraph composition (`GraphTemplate` substrate)  
**Code:** `mechaharness.graph_templates`  
**Requirements:** [Recipes and decision plane](./requirements/recipes-and-decision-plane.md)

**Agentic Recipes** are a top-level concept: concrete agent-control patterns
(fan-out, verify-repair, decision plane, bounded retry, …) that instantiate to
ordinary `ExecutionGraph` nodes. The factory API remains `GraphTemplate` /
soft points / registry — not a second executor. Prefer human-readable tiling
code; every shipped recipe needs an owning user story that names its catalog
id. Policies (`VerificationPolicy`, `DelegationPolicy`, `AdvisorPolicy`) remain
library-owned. Clients instantiate recipes and may retain concrete graphs.
See [Graph templates and Agentic Recipes](./reference/graph-templates.md) and
[Inspiration requirements map](./inspiration/requirements-map.md).

## Host extension

**Pattern:** Open identity + Config hooks  
**Code:** `.cursor/rules/host-extend.mdc`, `mechaharness.core.events`

A host app must add backends, harness families, tools, event types, grants, and
policies **without editing this repository**. That means class hierarchies and
namespaced strings (`core:agent_start`, `core:fs.write`, `acme:widget`), not closed enums or
`Literal` unions of names we own. Unknown namespaced values round-trip on the
wire. Default name maps in `SettingsConfig` are mergeable conveniences, not a
registry hosts must PR into.

Protocol vocabularies shared with model APIs (chat `Role`) may stay closed.
Identity of MechaHarness concepts must not.

**EventLog is not interception.** Append-only `EventLog` records are telemetry.
Lifecycle interception (inspiration req 20) is a separate ordered
`LifecycleExtensionRegistry` bound via Config (`get_lifecycle_extension_registry`),
invoked at declared boundaries such as before/after tool execution. Extensions
emit provenance events; they do not turn `FanoutEventLog` into a control plane.
Advisor counsel remains non-binding and distinct from interceptor block/replace.

## Inference Strategy

**Pattern:** Strategy  
**Code:** `mechaharness.inference`

Client code depends on `InferenceStrategy.complete()` / `stream()`, never on a
provider SDK. Strategies take `Settings` so pyiv can construct them. Add a backend
by subclassing `InferenceStrategy` and returning it from `get_inference_class()`
(or merging it into `inference_classes()`).

OpenAI-compatible HTTP covers many local servers (LM Studio, vLLM, Ollama’s
OpenAI mode) through one strategy (`OpenAICompatStrategy`) with different default
`base_url`s applied by `SettingsConfig`. Provider JSON is modeled in
`mechaharness.inference.openai_wire`; portable domain types stay in
`mechaharness.core.types`.

## Judge

**Pattern:** Strategy adapter over typed questions + injectable connection  
**Code:** `mechaharness.inference.judge`, `mechaharness.inference.systemone`,
`mechaharness.api_connection`, `mechaharness.judgement_policy`

`judge()` evaluates closed-world questions (`noul` / `choice` / `score`) and
returns a **Judgement**. HTTP reachability uses `APIConnectionConfig` (default
`SimpleHttpConnectionConfig` from `MECHA_JUDGE_*`). Pure `JudgementPolicy` /
`decide(...)` turns a Judgement into allow/deny/ask-human verdicts — models never
grant permission. Generative calls yield a **Completion**; media yields a
**Generation**. Tool grants remain `AccessPolicy`. See
[Judge reference](./reference/judge.md).

## Capability lanes

**Code:** `mechaharness.core.environment`

Hosts implement `InferenceEnvironment` with `active_lane()` (`reason`, `judge`,
`media`, or a host namespace). `AbstractHarness` calls `assert_compatible` before
tools that need grants or media. Wrong-lane errors name the operator load hint.

## Harness hierarchy

**Pattern:** Template method  
**Code:** `mechaharness.harness`

`AbstractHarness.run()` owns turn accounting, EventLog emits, cost pricing,
access checks, and tool execution. A harness is also a `Completer`: nested
harnesses share an `EventLog` and set `parent_agent_id`. Subclasses override
`should_stop` (and optionally `build_request` / `interpret_tool_calls` /
`tool_result_message` / `final_text`) for model-family behavior. Bind the
family with `get_harness_class()`.

| Family | Role |
|--------|------|
| `pass_through` | One inference call, then stop (no tools) |
| `tool_loop` | Native tool-calls until the model returns plain text |
| `react` | Textual Thought/Action/Observation loop |
| `openai_tools` | OpenAI-style tool-calling specialization |
| `anthropic_tools` | Anthropic tool_use specialization |

## Shared contract

**Code:** `mechaharness.core.types`, `mechaharness.core.contract`

`CompletionRequest`, `CompletionResponse`, `ChatMessage`, and tool models are
Pydantic and serialize cleanly. `RunRequest` / `RunResponse` are the OpenAPI
non-DI surface shared by CLI, HTTP, and `mechaharness.factory.run`.

## Frontends

**Code:** `mechaharness.cli`, `mechaharness.api`, `mechaharness.factory`

CLI and API are thin adapters over `run(RunRequest)`. They must not embed
provider-specific logic. `run()` builds a `SettingsConfig` and injects.
