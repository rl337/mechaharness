# Template: contract_extraction

Freeze verified discovery evidence into a typed `ChangeContract` before any
mutating coding step.

| Item | Value |
|------|-------|
| Name | `contract_extraction` |
| Module | `mechaharness.graph_templates.contract_extraction` |
| Class | `ContractExtractionTemplate` |
| Version | `1` |

## When to use

- After `workspace_discovery` publishes a `WorkspaceInventory`
- Before plan/execute stages that may edit the workspace
- When prior path+hash invariants must survive model proposals

## Topology

```text
seed → freeze (invariant_freeze) → propose (infer)
  → assemble (contract_assemble) → validate (contract_validate)
```

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `propose_payload` | task_state | ContextSpec / completion for semantic requirements |

## Node components

| Graph node | Components |
|------------|------------|
| `propose` | `soft_point` (`propose_payload`), `inference` |

## Stories

Suite `fangore_contract_extraction` (`005` shape, `010` found freeze).
