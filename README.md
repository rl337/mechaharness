# MechaHarness

![MechaHarness](docs/logo.png)

Python agentic harness that separates **how you call models** from **how you run agent loops**.

- **Inference Strategy** — swap OpenAI, Anthropic, LM Studio, vLLM, Ollama, or any OpenAI-compatible server
- **Harness hierarchy** — model-family architectures (tool-calling loops, ReAct, …) share one base loop
- **DI-first** — pyiv `MechaHarnessConfig` wires the graph; OpenAPI `RunRequest` / `run()` is the non-DI facade
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
          RunRequest / run()
                 │
                 ▼
        MechaHarnessConfig (pyiv)
                 │
                 ▼
        AbstractHarness  →  InferenceStrategy
```

Harnesses never import a provider SDK. They call `InferenceStrategy.complete()` with normalized `CompletionRequest` / `CompletionResponse` types (`src/mechaharness/core/types.py`). Design details: [`docs/architecture.md`](docs/architecture.md).

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

Non-DI (OpenAPI-shaped):

```python
import asyncio
from mechaharness import RunRequest, run

async def main() -> None:
    result = await run(RunRequest(prompt="What is 19 + 23?", backend="lmstudio"))
    print(result.final_text)

asyncio.run(main())
```

DI (pyiv Config hooks):

```python
from pyiv import get_injector

from mechaharness.di import MechaHarnessConfig
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.openai_compat import OpenAICompatStrategy


class MyConfig(MechaHarnessConfig):
    def get_inference_class(self):
        return OpenAICompatStrategy

    def get_harness_class(self):
        return ToolLoopHarness


injector = get_injector(MyConfig)
harness = injector.inject(AbstractHarness)
```

See [`docs/guides/dependency-injection.md`](docs/guides/dependency-injection.md).

## Extending

Subclass `InferenceStrategy` (constructor takes `Settings`) and return it from `get_inference_class()`, or merge it into `SettingsConfig.inference_classes()`. Subclass `AbstractHarness` and return it from `get_harness_class()`.

## Layout

```text
src/mechaharness/
  core/           # shared types, errors, OpenAPI RunRequest/RunResponse
  di.py           # MechaHarnessConfig / SettingsConfig (pyiv)
  inference/      # Strategy implementations
  harness/        # AbstractHarness hierarchy + families
  tools/          # ToolRegistry
  cli/            # Typer entrypoint
  api/            # FastAPI app
  factory.py      # non-DI run() helper
  config.py       # pydantic-settings
```

## Development

```bash
pip install -e ".[dev]"
./run_checks.sh
```

`run_checks.sh` is what CI runs: ruff, mypy, pytest, and CLI smoke (`version` / `backends` / `families`).

## Design notes

| Concern | Pattern | Why |
|--------|---------|-----|
| Wiring | pyiv Config hooks | DI-first; hosts inject MechaHarness types |
| Provider I/O | Strategy | Swap cloud/local without touching agent logic |
| Agent loop | Template method hierarchy | Share turn accounting; specialize stop/tool rules per model family |
| Frontends | OpenAPI `RunRequest` / `run()` | Same contract for CLI, HTTP, and non-DI Python |
| Bindings later | Pydantic + OpenAPI | Types stay serializable; API is the first non-Python client surface |
