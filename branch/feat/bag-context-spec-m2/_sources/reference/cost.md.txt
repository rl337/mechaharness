# Cost

Ledger and unit pricing for completer calls and successful tool runs, plus
graph-execution budgets. Modules: `mechaharness.core.access` (Ability units /
`CostAccountant`) and `mechaharness.budget` (`BudgetPolicy` / `Budget`).
Stability: evolving.

## Surface

| Item | Value |
|------|-------|
| Module | `mechaharness.core.access`, `mechaharness.budget` |
| Event | `core:cost` |
| Stability | evolving |

## Ability units

`Ability` ranks `simple` → `basic` → `intermediate` → `proficient` → `advanced`
cost **1, 2, 4, 8, 16** units. A `CapabilityProfile` sums those units (empty
profile counts as simple / 1). Tool cost is that tool's `ability.units`.

`InMemoryCostAccountant.price_inference()` / `price_tool()` append a
`CostEntry`, update the ledger, and emit `core:cost` when `agent_id` and
`run_id` are set. When a completer returns OpenAI-style `usage`, those
token counts are stored on the entry and on the run `CostReport` (local
Spark/$0 pricing can still use Ability units while tracking tokens).

## Graph budgets

`BudgetPolicy` declares optional `soft_limit` and `hard_limit` (abstract cost
units). `hard_limit=None` means unlimited. `GraphExecutor.run` **requires** a
`budget_policy`; node attempts charge a shared `Budget` (including nested
subgraphs). Soft breach cancels remaining open nodes and returns
`soft_exhausted`. Hard breach fails open nodes with prejudice
(`hard_budget_exceeded`). Stories: `fangore_insp_graph_budget`,
`fangore_insp_budget_subgraph_rollup`.

## Harness

`AbstractHarness` injects `CostAccountant` (required; Config binds
`InMemoryCostAccountant` on the shared `EventLog`). Each inference turn is priced after `complete()` and
passes through `CompletionResponse.usage`. Each successful tool run is priced
after invoke. Denied or unknown tools are not priced. `HarnessResult.cost` is
the ledger for that run. Thinking-model `reasoning_content` is kept on
`ChatMessage` and recorded on `core:inference`.

```python
from pyiv import get_injector

from mechaharness.core.events import InMemoryEventLog
from mechaharness.di import MechaHarnessConfig
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.mock import MockInferenceStrategy


class CostDemoConfig(MechaHarnessConfig):
    def __init__(self) -> None:
        self._log = InMemoryEventLog()
        super().__init__()

    def get_inference_class(self):
        return MockInferenceStrategy

    def get_harness_class(self):
        return PassThroughHarness

    def get_event_log(self):
        return self._log

    def get_harness_config(self):
        return HarnessConfig(model="mock")


harness = get_injector(CostDemoConfig).inject(AbstractHarness)
```

Tool grants are documented in [Access control](./access.md).
