# Architecture

MechaHarness keeps provider I/O and agent-loop policy as separate extension axes.

```text
┌─────────────┐     ┌─────────────┐
│  CLI (Typer)│     │ API (FastAPI)│
└──────┬──────┘     └──────┬──────┘
       │                   │
       └─────────┬─────────┘
                 ▼
        ┌────────────────┐
        │ AbstractHarness │  ← class hierarchy / template method
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
        └────────────────────┘
```

## Inference Strategy

**Pattern:** Strategy + registry  
**Code:** `mechaharness.inference`

Client code depends on `InferenceStrategy.complete()` / `stream()`, never on a
provider SDK. Register backends with `register_inference` and construct them via
`create_inference(name, **kwargs)`.

OpenAI-compatible HTTP covers many local servers (LM Studio, vLLM, Ollama’s
OpenAI mode) through one strategy with different default `base_url`s.

## Harness hierarchy

**Pattern:** Template method + family registry  
**Code:** `mechaharness.harness`

`AbstractHarness.run()` owns turn accounting, tool execution, and event
collection. Subclasses override `should_stop` (and optionally `build_request` /
`tool_result_message`) for model-family behavior.

| Family | Role |
|--------|------|
| `tool_loop` | Native tool-calls until the model returns plain text |
| `react` | Textual Thought/Action/Observation loop |
| `openai_tools` | OpenAI-style tool-calling specialization |
| `anthropic_tools` | Anthropic tool_use specialization |

## Shared contract

**Code:** `mechaharness.core.types`

`CompletionRequest`, `CompletionResponse`, `ChatMessage`, and tool models are
Pydantic and serialize cleanly — OpenAPI today, FFI/IPC later.

## Frontends

**Code:** `mechaharness.cli`, `mechaharness.api`, `mechaharness.factory`

CLI and API are thin adapters over `build_inference` / `build_harness`. They
must not embed provider-specific logic.
