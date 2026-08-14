# MechaHarness

![MechaHarness](docs/logo.png)

Python agentic harness that separates **how you call models** from **how you run agent loops**.

- **Inference Strategy** — swap OpenAI, Anthropic, LM Studio, vLLM, Ollama, or any OpenAI-compatible server
- **Harness hierarchy** — model-family architectures (tool-calling loops, ReAct, …) share one base loop
- **Frontends** — Typer CLI and FastAPI HTTP API (stable shapes for future language bindings)

Full documentation lives in [`docs/`](docs/index.md).

## Architecture

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

Harnesses never import a provider SDK. They call `InferenceStrategy.complete()` with normalized `CompletionRequest` / `CompletionResponse` types (`src/mechaharness/core/types.py`). Those Pydantic models are the portable contract for other languages later (OpenAPI today; FFI/IPC later).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# List backends / harness families
mechaharness backends
mechaharness families

# Local LM Studio (OpenAI-compatible)
mechaharness run "What is 2+2?" \
  --backend lmstudio \
  --family tool_loop \
  --model local-model

# OpenAI
export MECHA_API_KEY=sk-...
mechaharness run "Hello" --backend openai --model gpt-4o-mini

# HTTP API
mechaharness serve --port 8080
curl -s http://127.0.0.1:8080/health
```

Environment variables use the `MECHA_` prefix (`MECHA_API_KEY`, `MECHA_INFERENCE_BACKEND`, `MECHA_MODEL`, `MECHA_BASE_URL`, …).

## Library usage

```python
import asyncio
from mechaharness.factory import build_harness, build_inference
from mechaharness.tools import ToolRegistry

tools = ToolRegistry()

@tools.tool(
    description="Add two numbers",
    parameters={
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
        },
        "required": ["a", "b"],
    },
)
def add(a: float, b: float) -> str:
    return str(a + b)

async def main() -> None:
    inference = build_inference("lmstudio", model="local-model")
    harness = build_harness(
        "tool_loop",
        inference=inference,
        model="local-model",
        tools=tools,
        system_prompt="You are a careful assistant that uses tools when needed.",
    )
    result = await harness.run("What is 19 + 23?")
    print(result.final_text)
    await inference.aclose()

asyncio.run(main())
```

## Extending

### New inference backend (Strategy)

```python
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.registry import register_inference

class MyStrategy(InferenceStrategy):
    name = "my_provider"
    async def complete(self, request):
        ...

@register_inference("my_provider")
def _factory(**kwargs) -> InferenceStrategy:
    return MyStrategy(**kwargs)
```

### New harness family (Hierarchy)

Subclass `AbstractHarness` and override `should_stop` (and optionally `build_request` / `tool_result_message`), then `register_harness("my_family", MyHarness)`.

## Layout

```text
src/mechaharness/
  core/           # shared types + errors (public contract)
  inference/      # Strategy implementations + registry
  harness/        # AbstractHarness hierarchy + families
  tools/          # ToolRegistry
  cli/            # Typer entrypoint
  api/            # FastAPI app
  factory.py      # CLI/API wiring helpers
  config.py       # pydantic-settings
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

## Design notes

| Concern | Pattern | Why |
|--------|---------|-----|
| Provider I/O | Strategy + registry | Swap cloud/local without touching agent logic |
| Agent loop | Template method hierarchy | Share turn accounting; specialize stop/tool rules per model family |
| Frontends | Thin adapters over factory | Same wiring for CLI and API |
| Bindings later | Pydantic + OpenAPI | Types stay serializable; API is the first non-Python client surface |
