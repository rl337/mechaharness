# Template: fan_out_aggregate

Plan work, fan out independent branches, then aggregate with a fan-in budget.

| Item | Value |
|------|-------|
| Name | `fan_out_aggregate` |
| Module | `mechaharness.graph_templates.fan_out_aggregate` |
| Class | `FanOutAggregateTemplate` |
| Version | `1` |

## When to use

- Parallel research or multi-path exploration
- Map-style work that must join before continuing
- Any fan-out where write-scope conflicts should serialize at reduce time

## Topology

```text
plan → branch_0 … branch_N → reduce
```

Edges: `plan --control→ branch_*`, `branch_* --data→ reduce`.

## Soft points

| Name | Kind | Default | Notes |
|------|------|---------|-------|
| `plan_kind` | runner_kind | `plan` | Planning step runner |
| `branch_kind` | runner_kind | `branch` | Per-branch runner |
| `reduce_kind` | runner_kind | `reduce` | Aggregation runner |
| `branch_payloads` | task_state | `[{index:0}]` | Via `GraphTemplateParams.branch_payloads` |
| `fan_in_budget` | budget | `8` | Stored on reduce payload |
| `acceptance` | policy | `[]` | Attached to reduce |

## Example

```python
from mechaharness.graph_templates import (
    FanOutAggregateTemplate,
    GraphTemplateParams,
)

graph = FanOutAggregateTemplate().instantiate(
    GraphTemplateParams(
        goal="compare two drafts",
        branch_payloads=[
            {"index": 0, "source": "a"},
            {"index": 1, "source": "b", "write_scopes": ["draft"]},
        ],
        soft_bindings={"fan_in_budget": 4, "branch_kind": "research_branch"},
        acceptance=["merged"],
    )
)
assert list(graph.nodes) == ["plan", "branch_0", "branch_1", "reduce"]
```

## Tests

Fixture cases under `tests/fixtures/graph_templates/` (ids prefixed
`fan_out_aggregate_*`) exercise topology and soft-point overrides with static
Pydantic models — no live inference.
