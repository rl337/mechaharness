# Cost

Ledger and unit pricing for completer calls and successful tool runs. Module:
`mechaharness.core.access`. Stability: evolving.

## Surface

| Item | Value |
|------|-------|
| Module | `mechaharness.core.access` |
| Event | `core:cost` |
| Stability | evolving |

## Ability units

`Ability` ranks `simple` → `basic` → `intermediate` → `proficient` → `advanced`
cost **1, 2, 4, 8, 16** units. A `CapabilityProfile` sums those units (empty
profile counts as simple / 1). Tool cost is that tool's `ability.units`.

`InMemoryCostAccountant.price_inference()` / `price_tool()` append a
`CostEntry`, update the ledger, and emit `core:cost` when `agent_id` and
`run_id` are set.

## Harness

`AbstractHarness` injects `CostAccountant` (default `InMemoryCostAccountant` on
the same `EventLog`). Each inference turn is priced after `complete()`. Each
successful tool run is priced after invoke. Denied or unknown tools are not
priced. `HarnessResult.cost` is the ledger for that run.

```python
from mechaharness.core.access import InMemoryCostAccountant
from mechaharness.core.events import InMemoryEventLog
from mechaharness.harness.base import HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.mock import MockInferenceStrategy

log = InMemoryEventLog()
harness = PassThroughHarness(
    inference=MockInferenceStrategy(),
    config=HarnessConfig(model="mock"),
    event_log=log,
    cost=InMemoryCostAccountant(event_log=log),
)
```

Tool grants are documented in [Access control](./access.md).
