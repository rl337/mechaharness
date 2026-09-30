# Template: environment_repair

Diagnose substrate gaps, repair under a stop contract, then recheck before
dependent graph work continues.

| Item | Value |
|------|-------|
| Name | `environment_repair` |
| Module | `mechaharness.graph_templates.environment_repair` |
| Class | `EnvironmentRepairTemplate` |
| Version | `1` |

## When to use

- Missing secrets, routes, binaries, or capacity discovered at linkage
- Bounded “fix the env” subgraphs before resume
- Host profile / lane load failures that are mechanically remediable

## Topology

```text
diagnose → repair_env (repeating + StopContract) → recheck
```

## Soft points

| Name | Kind | Default | Notes |
|------|------|---------|-------|
| `diagnose_kind` | runner_kind | `env_diagnose` | |
| `repair_kind` | runner_kind | `env_repair` | Repeating |
| `recheck_kind` | runner_kind | `env_recheck` | |
| `stop_contract` | budget | max_iterations=2 | Via `params.stop_contract` |
| `acceptance` | policy | `["environment_ok"]` | On recheck |
| `diagnosis_inputs` | task_state | `{}` | Via `params.inputs` |

## Example

```python
from mechaharness.graph_templates import (
    EnvironmentRepairTemplate,
    GraphTemplateParams,
)

graph = EnvironmentRepairTemplate().instantiate(
    GraphTemplateParams(
        goal="restore media lane",
        inputs={"missing": ["core:media.image"]},
        acceptance=["environment_ok"],
    )
)
assert graph.nodes["repair_env"].repeating is True
assert graph.nodes["recheck"].acceptance == ["environment_ok"]
```

## Tests

See `tests/fixtures/graph_templates/environment_repair_*.json`.
