# Template: workspace_discovery

Read-only workspace discovery: enumerate, search, and verify evidence relevant
to a caller objective, then publish a typed `WorkspaceInventory`.

| Item | Value |
|------|-------|
| Name | `workspace_discovery` |
| Module | `mechaharness.graph_templates.workspace_discovery` |
| Class | `WorkspaceDiscoveryTemplate` |
| Version | `1` |

## When to use

- Locate source/test evidence for a natural-language objective before coding
- Distinguish `found` / `not_found` / `inconclusive` / `failed` with verified refs
- Keep discovery read-only (no workspace mutations, no change plan)

## Topology

```text
seed → preflight → manifest → hypotheses (infer)
  → search → extract → interpret (infer)
  → resolve → coverage → publish
```

## Soft points

| Name | Kind | Default | Notes |
|------|------|---------|-------|
| `hypotheses_payload` | task_state | ContextSpec defaults | I1 completion / context |
| `interpret_payload` | task_state | ContextSpec defaults | I2 completion / context / inspection |
| `manifest_max_files` | budget | `100` | Or `inputs.constraints.max_files` |
| `search_max_matches` | budget | `50` | Or `inputs.constraints.max_search_results` |
| `min_files_scanned` | budget | `1` | Coverage floor |

## Example

```python
from mechaharness.graph_templates import (
    GraphTemplateParams,
    WorkspaceDiscoveryTemplate,
)

graph = WorkspaceDiscoveryTemplate().instantiate(
    GraphTemplateParams(
        goal="Find division-by-zero handling",
        inputs={
            "goal": "Find division-by-zero handling",
            "workspace": {"root": "."},
            "constraints": {"read_only": True, "max_files": 100},
        },
    )
)
assert graph.template_name == "workspace_discovery"
assert graph.nodes["publish"].kind == "inventory_publish"
```

## Outputs

`out.workspace_inventory` (via hard `inventory_publish`):

- `status`: `found` | `not_found` | `inconclusive` | `failed`
- `relevant_files[]` / `tests[]` with verified paths and hashes
- `coverage`, `unknowns`, `rejected_claims`, `workspace_revision`

A model cannot force `found` without verified evidence.

## Node components

| Graph node | Components |
|------------|------------|
| `hypotheses` | `soft_point` (`hypotheses_payload`), `inference` |
| `interpret` | `soft_point` (`interpret_payload`), `inference` |
| `manifest` / `search` / budgets | `soft_point` for budget soft points when bound |

## Stories

Suite `fangore_workspace_discovery` (`010`–`080`): found, not_found,
inconclusive, failed, checkpoint, continuity, snapshot tools, negative control.
