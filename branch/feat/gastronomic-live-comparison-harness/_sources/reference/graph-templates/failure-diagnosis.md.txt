# Template: failure_diagnosis

Classify host-observed `VerificationReport` / execution failures into a typed
`Diagnosis` (failure class, evidence, next experiment).

| Item | Value |
|------|-------|
| Name | `failure_diagnosis` |
| Module | `mechaharness.graph_templates.failure_diagnosis` |
| Class | `FailureDiagnosisTemplate` |
| Version | `1` |

## When to use

- After `change_verification` publishes a failed (or green) `VerificationReport`
- When repair loops need a distinct, evidence-linked next experiment
- When model text must not invent failure causes

## Topology

```text
seed → constrain (diagnosis_constrain) → classify (diagnosis_classify)
  → publish (diagnosis_publish) → validate (diagnosis_validate)
```

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `diagnose_payload` | task_state | Optional classify parameters |

## Node components

| Graph node | Components |
|------------|------------|
| `classify` | `soft_point` (`diagnose_payload`) |

## Stories

Suite `fangore_failure_diagnosis` (`005` shape, `010` classify).
