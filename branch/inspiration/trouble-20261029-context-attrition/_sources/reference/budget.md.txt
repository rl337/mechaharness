# Budget (soft / hard spend)

Execution spend ceilings for graph and recipe runs. Module:
`mechaharness.budget`. Stability: evolving.

## Surface

| Item | Value |
|------|-------|
| Module | `mechaharness.budget` |
| Enforced by | `GraphExecutor` |
| Stability | evolving |

## Policy and ledger

`BudgetPolicy` declares optional `soft_limit` and `hard_limit` in abstract
cost units (`unit`: `units` | `usd` | `tokens`). `hard_limit=None` means
**unlimited**. Soft is optional; when both are set, soft must be `<=` hard.

`Budget` is the mutable spend ledger for one run. Nested subgraphs share the
ledger via `Budget.child()` so child `NodeOutcome.cost_units` count against
the parent ceiling.

| Level | Executor behavior |
|-------|-------------------|
| Soft | Wind down: cancel remaining open nodes; status `soft_exhausted`, error `soft_budget_exceeded` |
| Hard | Fail: status `failed`, error `hard_budget_exceeded` (charge is post-attempt) |

Default node cost is `1.0` when a runner does not set `cost_units`.

## SoftPoint `kind="budget"` is not this

Recipe soft-point `kind="budget"` means stop/turns / loop bounds — **not**
`BudgetPolicy`. Do not confuse the two.

## Host recipe-run pattern

Hosts pass spend ceilings the same way as authorization (see
[Access control](./access.md)):

1. **Per-run** — `run_recipe(..., budget_policy=BudgetPolicy(...))` or CLI
   `run_recipe` body field `budget: {soft_limit, hard_limit, unit}`.
2. **Instrumentor / story** — `environment.budget` on `user_story` binds a
   default on `CliInstrumentor`; omit → `BudgetPolicy.unlimited()`.
3. **Product verb** — `run_budgeted_graph` exercises a fixed compute graph
   under soft/hard or nested rollup (for acceptance walks).

```python
from mechaharness.budget import BudgetPolicy
from mechaharness.recipe_runner import run_recipe

await run_recipe(
    "verify_repair",
    runners=runners,
    budget_policy=BudgetPolicy(soft_limit=10, hard_limit=20),
    grants=["core:graph.execute"],
)
```

```yaml
environment:
  budget:
    soft_limit: 2
    hard_limit: null
    unit: units
```

Host-kit / adapters keep unlimited until a policy is supplied — intentional
no-op defaults.

## See also

- [Access control](./access.md) — grants + recipe-run kwargs
- [Host integration](../requirements/host-integration.md) — HOST-08
