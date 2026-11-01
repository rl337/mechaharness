# Template: gastronomic_guided_development

Product composition for gastronomic guided development. Discovery through
scoped execute, host verification, and failure diagnosis are tiled;
revision/acceptance stages are deferred. `guided_coding` remains the baseline
control.

| Item | Value |
|------|-------|
| Name | `gastronomic_guided_development` |
| Module | `mechaharness.graph_templates.gastronomic_guided_development` |
| Class | `GastronomicGuidedDevelopmentTemplate` |
| Version | `1` |

## Topology

```text
seed
  → discovery_tile (workspace_discovery)
  → contract_tile (contract_extraction)
  → plan_tile (change_decomposition)
  → execute_tile (change_execution)
  → verify_tile (change_verification)
  → diagnose_tile (failure_diagnosis)
  → publish / publish_verification / publish_execution / publish_plan /
    publish_contract / publish_inventory
```

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `discovery_bindings` | task_state | Forwarded to `workspace_discovery` |
| `contract_bindings` | task_state | Forwarded to `contract_extraction` |
| `plan_bindings` | task_state | Forwarded to `change_decomposition` |
| `execution_bindings` | task_state | Forwarded to `change_execution` |
| `verification_bindings` | task_state | Forwarded to `change_verification` |
| `diagnosis_bindings` | task_state | Forwarded to `failure_diagnosis` |
| `hypotheses_payload` | task_state | Optional discovery soft point |
| `interpret_payload` | task_state | Optional discovery soft point |
| `propose_payload` | task_state | Optional contract soft point |
| `plan_propose_payload` | task_state | Optional plan soft point |
| `apply_payload` | task_state | Optional execution soft point |
| `verify_payload` | task_state | Optional verification soft point |
| `diagnose_payload` | task_state | Optional diagnosis soft point |

## Node components

| Graph node | Components |
|------------|------------|
| `discovery_tile` | `child_graph` |
| `contract_tile` | `child_graph` |
| `plan_tile` | `child_graph` |
| `execute_tile` | `child_graph` |
| `verify_tile` | `child_graph` |
| `diagnose_tile` | `child_graph` |

## Stories

`fangore_gastronomic_guided_development_shape` in suite
`fangore_contract_extraction`.
