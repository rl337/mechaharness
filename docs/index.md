# MechaHarness docs

![MechaHarness](./logo.png)

Python agentic harness that separates **how you call models** from **how you run agent loops**.

Published site: [https://rl337.org/mechaharness/](https://rl337.org/mechaharness/)

## Contents

| Page | Description |
|------|-------------|
| [Architecture](./architecture.md) | Inference Strategy, harness hierarchy, pyiv Config |
| [Install & quick start](./guides/install.md) | Environment setup and first run |
| [Junespark](./guides/junespark.md) | Named OpenAI-compat LAN backend + live tests |
| [Dependency injection](./guides/dependency-injection.md) | Config hooks vs OpenAPI `run()` |
| [CLI reference](./reference/cli.md) | `mechaharness` commands |
| [HTTP API reference](./reference/api.md) | FastAPI routes |
| [Event log](./reference/events.md) | Structured `EventLog` emit / query |
| [Cost](./reference/cost.md) | Ability units, `CostAccountant`, `core:cost` |
| [Access control](./reference/access.md) | Namespaced grants, `AccessControl`, `core:access_check` |
| [Judge / decide](./reference/judge.md) | `judge()`, System One, policy verdicts, lanes |
| [ADR 0001](./adr/0001-pyiv-config.md) | Why Config hooks replaced string registries |

## Mental model

1. **Inference Strategy** — pluggable backends (`openai`, `anthropic`, `lmstudio`, `vllm`, `ollama`, …)
2. **Harness family** — agent-loop policy (`pass_through`, `tool_loop`, `react`, `openai_tools`, `anthropic_tools`)
3. **Frontends** — Typer CLI and FastAPI share `RunRequest` / `mechaharness.factory.run`
4. **DI** — `MechaHarnessConfig` binds interfaces; see [Dependency injection](./guides/dependency-injection.md)

Normalized types in `mechaharness.core.types` are the portable contract for future language bindings.
