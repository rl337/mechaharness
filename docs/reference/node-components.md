# Node components

**Node components** are sub-node elements that must render **within** a parent
[graph node](./graph-templates.md) (`GraphNode`). They are not free-floating
world-graph nodes.

Normative rules:
[Dynamic tool graph and node components](../requirements/dynamic-tool-graph.md).

| Surface | Value |
|---------|-------|
| Package | `mechaharness.node_component` |
| Stability | evolving |
| Kind rule | Kinds ⊆ existing MH events / soft points / nest / budget / effects |

## Vocabulary

| Term | Meaning |
|------|---------|
| Graph node | `GraphNode` in an `ExecutionGraph` |
| Node component | Sub-node element with required `parent_node_id` |

## Closed kind catalog (current)

| Kind | Source | Notes |
|------|--------|-------|
| `turn_start` | `core:turn_start` | Harness turn boundary |
| `inference` | `core:inference` | Model complete |
| `tool_call` | `core:tool_call` | One tool invocation |
| `tool_result` | `core:tool_result` | Tool outcome |
| `max_turns` | `core:max_turns` | Turn ceiling hit |
| `cost` | `core:cost` | Priced spend span |
| `access_check` | `core:access_check` | Grant allow/deny |
| `extension_applied` | `core:extension_applied` | Lifecycle extension fired |
| `soft_point` | `SoftPoint` on templates | Name + SoftPointKind |
| `child_graph` | `subgraph` / `child_run_id` | Handle to nested graph nodes |
| `stop_contract` | `repeating` + `StopContract` | Expandable / bound loop marker |
| `budget_level` | `BudgetLevel` | OK / soft / hard on shared ledger |
| `effect_state` | `EffectState` | Effectful node external lifecycle |

**Not node components:** `agent_*`, `run_*`, `graph_start` / `graph_end`,
`graph_node_start` / `graph_node_end` (node frame), checkpoint `GraphEvent`
transport.

## Query

```python
from mechaharness.node_component import node_components_for
from mechaharness.graph_templates import (
    FanOutAggregateTemplate, GraphTemplateParams,
)

graph = FanOutAggregateTemplate().instantiate(
    GraphTemplateParams(goal="demo", branch_payloads=[{"id": "a"}])
)
comps = node_components_for(graph)
assert all(c.parent_node_id for c in comps)
```

## Traversal

`traversal_from_events` projects EventLog-like payloads into component-aligned
records (parent + kind + status) for host lighting. Prefer aligning with
`RolloutGraph` via `execution_node_id` when a graph node exists.

## Recipe obligation

Every Agentic Recipe reference page SHOULD list node components per graph node
(see `.cursor/skills/agentic-recipes/SKILL.md`). Soft points are `soft_point`
components of the nodes that expose them.
