# Dependency injection

Host apps **must** wire MechaHarness through pyiv (`MechaHarnessConfig` →
`get_injector` → `inject(...)`). Manual `ToolLoopHarness(...)` construction is
not a supported host path. Prefer the OpenAPI-shaped `run()` helper only when
you want the facade that builds a Config under the hood.

Requires **pyiv ≥ 0.4.1** (qualified keys: `Named` / `Matched` / `Key`).

## Prerequisites

- MechaHarness installed (`pip install -e ".[dev]"`), which pulls in pyiv
- Familiarity with `InferenceStrategy` and `AbstractHarness` from [Architecture](../architecture.md)

## Steps

### 1. Subclass `MechaHarnessConfig`

Override the class hooks. `configure()` (called from the Config constructor)
class-binds inference and harness (singleton), aliases `Completer` to the
bound `InferenceStrategy`, and registers shared services (`EventLog`,
`AccessControl`, `CostAccountant`, judge connection/provider, …).

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

`AbstractHarness` constructor deps are required injectables: `Completer`,
`ToolRegistry`, `HarnessConfig`, `EventLog`, `AccessControl`, `CostAccountant`,
`InferenceEnvironment`. Opt into EventLog query tools with
`include_subagent_tools()` → `HarnessConfig.subagent_tools`.

Host apps that already have a Config should subclass `MechaHarnessConfig` and
call `super().configure()` before registering their own types. Tests may use
`pyiv.override(base).with_(overrides)` to swap doubles.

### 2. Name maps for CLI/HTTP-style selection

`SettingsConfig` looks up `Settings.inference_backend` and
`Settings.harness_family` in overridable maps. Add a backend by overriding
`inference_classes()`:

```python
from mechaharness.di import SettingsConfig


class AppConfig(SettingsConfig):
    def inference_classes(self):
        classes = super().inference_classes()
        classes["mine"] = MyStrategy
        return classes
```

### 3. Non-DI OpenAPI path

```python
import asyncio
from mechaharness import RunRequest, run

result = asyncio.run(run(RunRequest(prompt="Hello", backend="lmstudio")))
print(result.final_text)
```

`run()` still constructs a `SettingsConfig` and injects; it only hides pyiv from
the caller.

Override `get_access_policy()` / `get_grants()` (or `get_access_control()`) to
inject deny-by-default tool grants; use `CompoundPolicy` to union reusable
`AccessPolicy` layers. See [Access control](../reference/access.md).

For durable plans, override `get_node_runner_registry()`,
`get_graph_failure_policy()`, `get_graph_escalation()`, and optionally
`get_linkage_resolver()` / `get_graph_template_registry()` /
`get_capability_envelope()`, then `injector.inject(GraphExecutor)`. Include
`core:graph.execute` (and `core:graph.escalate` when using escalation) in
grants. Library templates are owned by MechaHarness; June instantiates them.
See [Architecture](../architecture.md) and
[Inspiration requirements map](../inspiration/requirements-map.md).

## Verify

- `injector.inject(AbstractHarness)` returns your harness family
- `injector.inject(GraphExecutor)` returns the bound executor
- `pytest tests/test_di.py` / `tests/test_graph_executor.py` pass
- Unknown `--backend` / `family` names raise `KeyError` listing known maps

## Next

- [Architecture](../architecture.md) (including host extension)
- [Install](./install.md)
