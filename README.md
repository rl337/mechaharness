# MechaHarness

![MechaHarness](docs/logo.png)

Python **agent harness** for hosts that compose inference safely — not a thin
chat-client wrapper. Founding principles:

1. **Modular via dependency injection** — pyiv `MechaHarnessConfig`; hosts
   subclass and compose (no forked enums / string registries)
2. **Multi-model / lanes native** — reason, judge, and media lanes;
   `Completion` / `Judgement` / `Generation` outcomes
3. **Cost in the object model** — `CostAccountant` on the harness path so runs
   cannot quietly go AWOL on spend
4. **EventLog telemetry built in** — queryable lifecycle, inference, tools,
   cost, and access events on every run

Also: deny-by-default grants / `CompoundPolicy`, and host-extendable open
identity. Docs: [https://rl337.org/mechaharness/](https://rl337.org/mechaharness/)

## Install

```bash
pip install mechaharness
```

Requires Python 3.9+. Unreleased `main`:

```bash
pip install git+https://github.com/rl337/mechaharness.git
```

## Quick start

```bash
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

See [Dependency injection](https://rl337.org/mechaharness/guides/dependency-injection.html).

## Extending

Subclass `InferenceStrategy` (constructor takes `Settings`) and return it from `get_inference_class()`, or merge it into `SettingsConfig.inference_classes()`. Subclass `AbstractHarness` and return it from `get_harness_class()`.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs]"
./run_checks.sh
```

`run_checks.sh` is what CI runs: ruff, mypy, pytest, Sphinx, and CLI smoke. EventLog + cost without a GPU:

```bash
mechaharness run "What is 2+2?" --backend mock --family pass_through --model mock --json
```

## Design notes

| Concern | Pattern | Why |
|--------|---------|-----|
| Wiring | pyiv Config hooks | DI-first; hosts inject MechaHarness types |
| Provider I/O | Strategy | Swap cloud/local without touching agent logic |
| Agent loop | Template method hierarchy | Share turn accounting; specialize stop/tool rules per model family |
| Frontends | OpenAPI `RunRequest` / `run()` | Same contract for CLI, HTTP, and non-DI Python |
| Bindings later | Pydantic + OpenAPI | Types stay serializable; API is the first non-Python client surface |
