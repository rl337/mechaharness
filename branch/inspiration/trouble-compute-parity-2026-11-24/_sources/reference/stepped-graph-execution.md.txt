# Stepped graph execution

Pause and continue `GraphExecutor` walks between nodes. Module:
`mechaharness.graph_executor` (`RunControl`, `GraphResult.status=paused`).
CLI: `graph_walk`. Normative: [stepped-graph-execution requirements](../requirements/stepped-graph-execution.md).

Stability: evolving (SG stories landing).

## Control

| Mode | Behavior |
|------|----------|
| `to_completion` | Default; run until terminal |
| `one_step` | One frontier advance, then `paused` |
| `until` | Advance until `until` node id; `stop: before` \| `after` |

Soft/subgraph: one step **enters** the call site and stops before the child's
first node.

## CLI (`graph_walk`)

| action | Role |
|--------|------|
| `start` | Bind inline graph + optional `until` / `one_step` |
| `step` | `one_step` from session checkpoint |
| `until` | Run until named node |
| `continue` | Resume to completion (or further until) |
| `set_live_epoch` | Set `live_authorization_epoch` between pauses |

## Story shape

```yaml
graph:
  inline:
    goal: publish
    nodes:
    - {id: plan, kind: compute}
    - {id: publish, kind: publish, depends_on: [plan], payload: {tool_phase: execute}}
steps:
- do: {graph_walk: {action: start, until: publish, stop: before}}
- do: {graph_walk: {action: set_live_epoch, live_authorization_epoch: 3}}
- do: {graph_walk: {action: continue}}
```

## Nested call returns

`GraphExecutor` checkpoints each active frame and resumes callers after a child
commits its return. `GraphResult.frame_path` identifies the root-to-active-frame
run IDs while paused. `ExecutionGraph.frame_path`, `frame_spent`, and
`frame_return` persist frame metadata alongside `walk_bag`; legacy checkpoints
default to an empty path and no return record.

The `fangore_recursive_return` and `fangore_inference_frame_return` acceptance
stages cover recursive calls and inference results returning through two
callers in the `fangore_bag_inference_continuity` suite. See the
[requirements](../requirements/stepped-graph-execution.md) for return and
resume invariants.
