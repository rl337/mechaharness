# Architecture

MechaHarness keeps provider I/O and agent-loop policy as separate extension axes.
Wiring is **pyiv dependency injection first**. OpenAPI (`RunRequest` / `run()`) is
the non-DI facade, not a second architecture. See `.cursor/rules/di-first.mdc`.

```text
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

**Pattern:** Template-method pyiv `Config` + constructor injection  
**Code:** `mechaharness.di`

`MechaHarnessConfig.configure()` binds `InferenceStrategy`, `AbstractHarness`,
`Settings`, `HarnessConfig`, `ToolRegistry`, `EventLog`, and `CostAccountant`. Subclasses override
`get_inference_class()` and `get_harness_class()` (called from the Config
constructor). Host apps subclass `MechaHarnessConfig`, call `super().configure()`,
and `injector.inject(AbstractHarness)` — or inject those types into their own
services.

`SettingsConfig` implements the hooks via overridable `inference_classes()` /
`harness_classes()` maps plus `Settings.inference_backend` /
`Settings.harness_family`. That is the configuration path for CLI/HTTP callers
who pick backends by name.

Do not add string registries or a global injector. Domain types stay pyiv-free.

## Host extension

**Pattern:** Open identity + Config hooks  
**Code:** `.cursor/rules/host-extend.mdc`, `mechaharness.core.events`

A host app must add backends, harness families, tools, event types, and
policies **without editing this repository**. That means class hierarchies and
namespaced strings (`core:agent_start`, `acme:widget`), not closed enums or
`Literal` unions of names we own. Unknown namespaced values round-trip on the
wire. Default name maps in `SettingsConfig` are mergeable conveniences, not a
registry hosts must PR into.

Protocol vocabularies shared with model APIs (chat `Role`) may stay closed.
Identity of MechaHarness concepts must not.

## Inference Strategy

**Pattern:** Strategy  
**Code:** `mechaharness.inference`

Client code depends on `InferenceStrategy.complete()` / `stream()`, never on a
provider SDK. Strategies take `Settings` so pyiv can construct them. Add a backend
by subclassing `InferenceStrategy` and returning it from `get_inference_class()`
(or merging it into `inference_classes()`).

OpenAI-compatible HTTP covers many local servers (LM Studio, vLLM, Ollama’s
OpenAI mode) through one strategy (`OpenAICompatStrategy`) with different default
`base_url`s applied by `SettingsConfig`.

## Harness hierarchy

**Pattern:** Template method  
**Code:** `mechaharness.harness`

`AbstractHarness.run()` owns turn accounting, EventLog emits, cost pricing, and
tool execution. Subclasses override `should_stop` (and optionally `build_request` /
`tool_result_message`) for model-family behavior. Bind the family with
`get_harness_class()`.

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
