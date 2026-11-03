# Template: strategy_revision

Deterministic retry / stop / yield gate over a typed `Diagnosis` (plus plan and
retry history). Every retry requires an evidence delta or an explicit strategy
change / stop / yield.

| Item | Value |
|------|-------|
| Name | `strategy_revision` |
| Module | `mechaharness.graph_templates.strategy_revision` |
| Class | `StrategyRevisionTemplate` |
| Version | `1` |

## When to use

- After `failure_diagnosis` publishes a `Diagnosis`
- When repair loops must not repeat the same experiment unbounded
- When disposition must be host-gated, not model-asserted

## Topology

```text
seed → constrain (revision_constrain) → decide (revision_decide)
  → publish (revision_publish) → validate (revision_validate)
```

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `revise_payload` | task_state | Optional decide parameters (`attempts_max`, …) |

## Node components

| Graph node | Components |
|------------|------------|
| `decide` | `soft_point` (`revise_payload`) |

## Stories

Suite `fangore_strategy_revision` (`005` shape, `010` retry, `015` accept,
`020` stop, `025` change, `030` yield).
