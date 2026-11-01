# Template: change_verification

Host-observe a `ChangeExecution` against `ChangeContract` checks and publish a
typed `VerificationReport` (verify_runs + immutable hash invariants).

| Item | Value |
|------|-------|
| Name | `change_verification` |
| Module | `mechaharness.graph_templates.change_verification` |
| Class | `ChangeVerificationTemplate` |
| Version | `1` |

## When to use

- After `change_execution` publishes a `ChangeExecution`
- When verification evidence must be host-observed (not model text)
- When untouched immutable invariants must stay green

## Topology

```text
seed → constrain (verification_constrain) → run (verification_run)
  → publish (verification_publish) → validate (verification_validate)
```

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `verify_payload` | task_state | Optional extra verify_runs / parameters |

## Node components

| Graph node | Components |
|------------|------------|
| `run` | `soft_point` (`verify_payload`) |

## Stories

Suite `fangore_change_verification` (`005` shape, `010` host).
