# Template: verify_repair

Produce an artifact, verify it, then repair under an explicit stop contract.

| Item | Value |
|------|-------|
| Name | `verify_repair` |
| Module | `mechaharness.graph_templates.verify_repair` |
| Class | `VerifyRepairTemplate` |
| Version | `1` |

## When to use

- Code/doc edits that must pass deterministic checks before completion
- Any produce → verify → bounded fix loop
- When “answer generated” must not imply “task complete”

## Topology

```text
produce → verify → repair (repeating + StopContract) → complete
```

## Soft points

| Name | Kind | Default | Notes |
|------|------|---------|-------|
| `produce_kind` | runner_kind | `produce` | |
| `verify_kind` | runner_kind | `verify` | |
| `repair_kind` | runner_kind | `repair` | Repeating |
| `complete_kind` | runner_kind | `complete` | |
| `stop_contract` | budget | max_iterations=3 | Via `params.stop_contract` |
| `acceptance` | policy | `[]` | On verify/complete |
| `produce_inputs` | task_state | `{}` | Via `params.inputs` |

## Example

```python
from mechaharness.graph_templates import GraphTemplateParams, VerifyRepairTemplate
from mechaharness.stop_contract import StopContract

graph = VerifyRepairTemplate().instantiate(
    GraphTemplateParams(
        goal="fix lint failures",
        inputs={"path": "src/"},
        acceptance=["tests_green"],
        stop_contract=StopContract(version="1", max_iterations=5),
    )
)
assert graph.nodes["repair"].repeating is True
assert graph.nodes["repair"].stop_contract is not None
```

## Tests

See `tests/fixtures/graph_templates/verify_repair_*.json`.
