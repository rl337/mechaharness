# Template: change_decomposition

Decompose a typed `ChangeContract` into ordered `ChangePlan` slices before any
mutating coding step.

| Item | Value |
|------|-------|
| Name | `change_decomposition` |
| Module | `mechaharness.graph_templates.change_decomposition` |
| Class | `ChangeDecompositionTemplate` |
| Version | `1` |

## When to use

- After `contract_extraction` publishes a `ChangeContract`
- Before execute/verify stages that may edit the workspace
- When slices need scope, checks, rollback, and dependency order

## Topology

```text
seed → constrain (plan_constrain) → propose (infer)
  → assemble (plan_assemble) → validate (plan_validate)
```

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `propose_payload` | task_state | ContextSpec / completion for ordered slices |

## Node components

| Graph node | Components |
|------------|------------|
| `propose` | `soft_point` (`propose_payload`), `inference` |

## Stories

Suite `fangore_change_decomposition` (`005` shape, `010` ordered slices).
