# Template: change_execution

Apply one approved `ChangePlan` slice with scoped file revisions and an explicit
write grant, then publish a typed `ChangeExecution` (diff + hashes).

| Item | Value |
|------|-------|
| Name | `change_execution` |
| Module | `mechaharness.graph_templates.change_execution` |
| Class | `ChangeExecutionTemplate` |
| Version | `1` |

## When to use

- After `change_decomposition` publishes a `ChangePlan`
- When applying exactly one approved slice before verification
- When scope escape must be refused and write grant must be explicit

## Topology

```text
seed → constrain (execution_constrain) → apply (execution_apply)
  → publish (execution_publish) → validate (execution_validate)
```

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `apply_payload` | task_state | Optional apply parameters / inline revisions |

## Node components

| Graph node | Components |
|------------|------------|
| `apply` | `soft_point` (`apply_payload`) |

## Stories

Suite `fangore_change_execution` (`005` shape, `010` apply).
