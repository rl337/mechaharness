# Template: gastronomic_guided_development

Product-level Agentic Recipe skeleton for gastronomic guided development.
Increment 1 tiles read-only discovery then contract extraction. Mutating
coding stages are deferred. `guided_coding` remains the baseline control.

| Item | Value |
|------|-------|
| Name | `gastronomic_guided_development` |
| Module | `mechaharness.graph_templates.gastronomic_guided_development` |
| Class | `GastronomicGuidedDevelopmentTemplate` |
| Version | `1` |

## Topology

```text
seed → discovery_tile (workspace_discovery)
  → contract_tile (contract_extraction)
  → publish / publish_inventory
```

Child bags use explicit `bag_inputs` / `bag_outputs` so discovery inventory
lands on `acc.stages.discovery` and the contract on `acc.stages.contract`.

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `discovery_bindings` | task_state | Forwarded to `workspace_discovery` |
| `contract_bindings` | task_state | Forwarded to `contract_extraction` |
| `hypotheses_payload` / `interpret_payload` / `propose_payload` | task_state | Optional passthrough soft points |

## Node components

| Graph node | Components |
|------------|------------|
| `discovery_tile` / `contract_tile` | `child_graph` |
| soft points | `soft_point` on seed / tiles as derived |

## Stories

`fangore_gastronomic_guided_development_shape` in suite
`fangore_contract_extraction`.
