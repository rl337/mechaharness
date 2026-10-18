# Dependency injection

Host apps **must** wire MechaHarness through pyiv (`MechaHarnessConfig` →
`get_injector` → `inject(...)`). Manual `ToolLoopHarness(...)` construction is
not a supported host path. Prefer the OpenAPI-shaped `run()` helper only when
you want the facade that builds a Config under the hood.

Requires **pyiv ≥ 1.0** (`Named` / `Matched` / `Key`, `Annotated[...]`
constructor injection, and injectable `AsyncHttpClient`). Prefer
`from mechaharness.di import get_injector` so Named Completer aliases bind
correctly.

## Prerequisites

- MechaHarness installed (`pip install -e ".[dev]"`), which pulls in pyiv
- Familiarity with `InferenceStrategy` and `AbstractHarness` from [Architecture](../architecture.md)

## Steps

### 1. Subclass `MechaHarnessConfig`

Override the class hooks. `configure()` (called from the Config constructor)
class-binds inference and harness (singleton), aliases `Completer` to the
bound `InferenceStrategy`, registers Named Completer / JudgeProvider bindings
from `completer_bindings()` / `judge_bindings()`, and registers shared services
(`EventLog`, `AccessControl`, `CostAccountant`, judge connection, …).

```python
from mechaharness.di import MechaHarnessConfig, get_injector
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

### 2. Lanes vs Completer flavors

**Lanes** (`reason` / `judge` / `media` on `InferenceEnvironment`) are
capability partitions for load hints and access. They are not DI qualifiers.

**Flavors** are multiple Completer (or JudgeProvider) bindings in one injector,
distinguished by pyiv `Named` tag sets (lane tag + host tags such as `code`,
`deep`, or `acme:…`). Declare them on Config; select them on host constructors
with `Annotated`:

```python
from typing import Annotated, Optional

from pyiv.key import Named, Matched
from pyiv.provider import Provider

from mechaharness.core.completer import Completer
from mechaharness.di import MechaHarnessConfig
from mechaharness.inference.judge import JudgeProvider


class AppConfig(MechaHarnessConfig):
    def completer_bindings(self):
        return [
            (Named(["reason"], default=True), self.get_inference_class()),
            (Named(["reason", "code", "deep"]), CodeCompleter),
            (Named(["reason", "summarize"]), SummarizeCompleter),
        ]

    def judge_bindings(self):
        return [
            (Named(["judge"], default=True), self.get_judge_provider()),
            (Named(["judge", "heavy"]), HeavyJudgeProvider),
        ]


class CodeReviewHarness(AbstractHarness):
    def __init__(
        self,
        inference: Annotated[Completer, Named(["reason", "code", "deep"])],
        tools: ToolRegistry,
        *,
        config: HarnessConfig,
        event_log: EventLog,
        access: AccessControl,
        cost: CostAccountant,
        environment: InferenceEnvironment,
        summarize: Annotated[
            Optional[Completer],
            Matched(required=["reason", "summarize"]),
        ] = None,
        judge: Annotated[Provider[JudgeProvider], Named(["judge", "heavy"])] | None = None,
    ) -> None:
        ...
```

Rules of thumb:

- Register with `Named` only (never `Matched` / `Annotated` on `register_key`).
- Exactly one `Named(..., default=True)` per type (or a single binding).
- Prefer constructor injection; `inject_members` / fields ignore `Annotated`.
- Do not invent marker ABC lanes or new `active_lane()` values for flavors.

### 3. Name maps for CLI/HTTP-style selection

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

### 4. Non-DI OpenAPI path

```python
import asyncio
from mechaharness import RunRequest, run

result = asyncio.run(run(RunRequest(prompt="Hello", backend="lmstudio")))
print(result.final_text)
```

`run()` still constructs a `SettingsConfig` and injects; it only hides pyiv from
the caller.

### HTTP transport (`AsyncHttpClient`)

`MechaHarnessConfig` registers a shared pyiv `AsyncHttpClient`
(`AsyncUrllibHttpClient` by default). Inference and judge adapters
(`OpenAICompatStrategy`, `AnthropicStrategy`, `SystemOneJudgeProvider`) take it
as a constructor dependency and send absolute URLs with per-request headers —
endpoint ownership stays on `Settings` / `APIConnectionConfig`.

In tests, bind a double instead of hitting the network:

```python
from pyiv.http import AsyncHttpClient, MemoryAsyncHttpClient

from mechaharness.di import MechaHarnessConfig


class TestConfig(MechaHarnessConfig):
    def configure(self):
        super().configure()
        client = MemoryAsyncHttpClient()
        client.add(
            "POST",
            "http://api.test/v1/chat/completions",
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )
        self.register_instance(AsyncHttpClient, client)
```

Hosts may register any `AsyncHttpClient` implementation (including a custom
httpx-backed client) without changing adapters.

Override `get_access_policy()` / `get_grants()` (or `get_access_control()`) to
inject deny-by-default tool grants; use `CompoundPolicy` to union reusable
`AccessPolicy` layers. See [Access control](../reference/access.md).

For durable plans, override `get_node_runner_registry()`,
`get_graph_failure_policy()`, `get_graph_escalation()`,
`get_checkpoint_store()` (default ephemeral EventLog adapter; use
`SqliteCheckpointStore` for process-restart durability), and optionally
`get_linkage_resolver()` / `get_capability_envelope()` /
`get_lifecycle_extension_registry()`, then `injector.inject(GraphExecutor)`.
Agentic Recipe membership is a pyiv map multibind: override
`graph_template_classes()` (merge via `super()`), discover with
`catalog_keys(GraphTemplate)`, and inject `GraphTemplateRegistry`. Backend and
harness family names use the same pattern (`inference_classes` /
`harness_classes` → `catalog_keys`). Include `core:graph.execute` (and
`core:graph.escalate` when using escalation) in grants. Ordered lifecycle
extensions (inspiration req 20) bind via `get_lifecycle_extension_registry()`
and are distinct from EventLog telemetry. Library templates are owned by
MechaHarness; clients instantiate them via Config and may retain the resulting
concrete graphs. See [Architecture](../architecture.md) and
[Graph templates](../reference/graph-templates.md).

### Host kit (readable GraphExecutor wiring)

Prefer `mechaharness.host_kit` when a host only needs to register runners and
choose checkpoint durability. It keeps the blessed path
(`MechaHarnessConfig` → `inject(GraphExecutor)`) without ten-line hand assembly
of EventLog / access / linkage / checkpoint / crash probe.

Owning acceptance stories: `fangore_host_kit_submit_once`,
`fangore_host_kit_event_tap` (HF-05 `event_log=` / `tapping_event_log`).
Executable examples live as pydoc doctests on `src/mechaharness/host_kit.py`
(run via `pytest --doctest-modules`) and as the fixture matrix under
`tests/fixtures/host_kit/`.

```python
import asyncio
from mechaharness.budget import BudgetPolicy
from mechaharness.external_effect import EffectDispatchResult
from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.host_kit import (
    SubmitOnceEffectfulRunner,
    effectful_external_handle,
    host_graph_executor,
)

async def submit(node, effect, context):
    del effect, context
    return EffectDispatchResult(external_handle=f"job-{node.payload['task_id']}")

runner = SubmitOnceEffectfulRunner(
    kinds=["coding_job"],
    backend_id="host.coding",
    submit=submit,
)
executor = host_graph_executor(runners=[runner], checkpoint_path="runs.sqlite")
graph = ExecutionGraph(goal="dispatch")
graph.add_node(
    GraphNode(id="coding_job", kind="coding_job", payload={"task_id": "t1"})
)
result = asyncio.run(
    executor.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="run-1",
        skip_linkage=True,
    )
)
assert result.status == "ok"
assert effectful_external_handle(result, "coding_job") == "job-t1"
```

#### What each helper owns

| Helper | Role |
|--------|------|
| `host_graph_executor` | Config subclass + inject; optional SQLite via `checkpoint_path` or a custom `checkpoint_store`; optional `event_log=` tap; default grants `GraphExecute` / `GraphEscalate` |
| `tapping_event_log` | EventLog wrapper that forwards emits to a host callback (HF-05) |
| `SubmitOnceEffectfulRunner` | Non-idempotent external effect: submit once, complete on accept, never silent-redispatch `UNCERTAIN` without a handle |
| `effectful_external_handle` | Read `external_run_id` / `external_handle` from a `GraphResult` without scraping node maps |

`SubmitOnceEffectfulRunner` completes the **graph node** when the backend
accepts a handle. Long-running job observation (poll until finished) remains a
host control-loop concern. Pass `checkpoint_store` **or** `checkpoint_path`,
not both. Omit both for the default ephemeral EventLog-backed store.

Related: [Transactional durable resume](../requirements/transactional-durable-resume.md)
(`fangore_transactional_durable_resume`) owns the crash-window contract this kit
sits on.

## Verify

- `injector.inject(AbstractHarness)` returns your harness family
- `injector.inject(GraphExecutor)` returns the bound executor
- `pytest tests/test_di.py` / `tests/test_graph_executor.py` /
  `tests/test_host_kit.py` pass
- Unknown `--backend` / `family` names raise `KeyError` listing known maps

## Next

- [Architecture](../architecture.md) (including host extension)
- [Install](./install.md)
