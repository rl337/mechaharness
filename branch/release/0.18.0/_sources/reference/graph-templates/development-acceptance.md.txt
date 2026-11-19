# Template: development_acceptance

Deterministic `DevelopmentOutcome` (`completed | needs_guidance | failed`) from
host gates over contract, verification, execution, and strategy revision.
Optional judge opinion is advisory only.

| Item | Value |
|------|-------|
| Name | `development_acceptance` |
| Module | `mechaharness.graph_templates.development_acceptance` |
| Class | `DevelopmentAcceptanceTemplate` |
| Version | `1` |

## When to use

- After `strategy_revision` publishes a disposition
- When the product result must be evidence-backed, not model-asserted
- When an optional independent judge may advise but must not override host gates

## Topology

```text
seed → constrain (acceptance_constrain) → decide (acceptance_decide)
  → publish (acceptance_publish) → validate (acceptance_validate)
```

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `accept_payload` | task_state | Optional decide parameters / advisory judge |

## Node components

| Graph node | Components |
|------------|------------|
| `decide` | `soft_point` (`accept_payload`) |

## Stories

Suite `fangore_development_acceptance` (`005` shape, `010` completed,
`015` guidance, `020` failed, `025` judge advisory).
