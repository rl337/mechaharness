# Cost

Ledger and unit pricing for completer calls. Module: `mechaharness.core.access`.
Stability: evolving. Access control (tool grants) is not wired yet.

## Surface

| Item | Value |
|------|-------|
| Module | `mechaharness.core.access` |
| Event | `core:cost` |
| Stability | evolving |

## Ability units

`Ability` ranks `simple` → `basic` → `intermediate` → `proficient` → `advanced`
cost **1, 2, 4, 8, 16** units. A `CapabilityProfile` sums those units (empty
profile counts as simple / 1).

`InMemoryCostAccountant.price_inference()` appends a `CostEntry`, updates the
ledger, and emits `core:cost` when `agent_id` and `run_id` are set.

## Harness

`AbstractHarness` injects `CostAccountant` (default `InMemoryCostAccountant` on
the same `EventLog`). Each inference turn is priced after `complete()`.
`HarnessResult.cost` is the ledger for that run.

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
