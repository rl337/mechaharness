# Dependency injection

Use pyiv to wire MechaHarness, or call the OpenAPI-shaped `run()` helper if you
do not want to touch injectors.

## Prerequisites

- MechaHarness installed (`pip install -e ".[dev]"`), which pulls in pyiv
- Familiarity with `InferenceStrategy` and `AbstractHarness` from [Architecture](../architecture.md)

## Steps

### 1. Subclass `MechaHarnessConfig`

Override the class hooks. `configure()` (called from the Config constructor)
registers those classes against the interfaces.

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

Host apps that already have a Config should subclass `MechaHarnessConfig` and
call `super().configure()` before registering their own types.

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

## Verify

- `injector.inject(AbstractHarness)` returns your harness family
- `pytest tests/test_di.py` passes
- Unknown `--backend` / `family` names raise `KeyError` listing known maps

## Next

- [Architecture](../architecture.md) (including host extension)
- [Install](./install.md)
