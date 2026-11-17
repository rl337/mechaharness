# Stepped graph execution (SG-*)

Normative product control for **pausing a graph walk between nodes** so hosts
and user stories can mutate live authority (or answer soft points) mid-run.
This is a first-class `GraphExecutor` / CLI surface — not a test-only debugger.

**Status:** implemented with owning user stories (`fangore_graph_*`,
`fangore_insp_effect_revalidation`).

## Motivation

MH-DOTS-02 (effect revalidation) and similar claims need:

> start → stop *before* a consequential `execute` node → change live
> authorization → continue → observe `revalidation_failed`.

Default `GraphExecutor.run` goes to completion. Stepped control returns to the
caller after a bounded advance while preserving checkpoints.

## Vocabulary

| Term | Meaning |
|------|---------|
| **to_completion** | Today's default: run until terminal status. |
| **one_step** | Advance exactly one frontier action, then pause. |
| **until** | Run until a named node id, then pause (`stop: before` or `after`). |
| **soft / subgraph enter** | Selecting a subgraph (soft) node as the frontier **is** one step: open the child frame and stop **before** the child's first node (debugger “break at call”). |
| **paused** | Non-terminal `GraphResult.status`; checkpoint saved; no final `GraphEnd` until a later continue reaches a terminal state. |

## Requirements

| ID | Requirement |
|----|-------------|
| SG-01 | `GraphExecutor.run` accepts optional run control: `mode` ∈ {`to_completion`, `one_step`, `until`}, `until` node id, `stop` ∈ {`before`, `after`}. Default remains `to_completion`. |
| SG-02 | `until` + `stop=before` pauses when that node is the next ready frontier **without** executing it (or entering a soft node). |
| SG-03 | `until` + `stop=after` executes through that node (leaf) or completes soft enter+… — for leaves: run the node then pause. |
| SG-04 | `one_step` on a leaf executes that leaf then pauses. |
| SG-05 | `one_step` on a subgraph/soft node **enters** the child (parent `RUNNING`, child checkpointed) and pauses before the child's first ready node. Does not run the first child statement in the same step. |
| SG-06 | Resume (`resume=True`) continues the same `run_id` from checkpoint under the same control knobs. |
| SG-07 | `GraphResult.status` may be `paused` with `stopped_before` (node id) and optional `entered_node_id` (soft call site). |
| SG-08 | Live authorization for effect revalidation remains `executor.live_authorization_epoch`; hosts/stories may change it between paused steps. |
| SG-09 | Product CLI verb `graph_walk` drives start / step / until / continue / set_live_epoch against an instrumentor-held session (inline graph or prior start). |
| SG-10 | User stories own the claims; no `debug_*` verbs. |

## Out of scope

- Decorating every edge automatically when a “debug flag” is on.
- Replacing durable `advice_requested` yields (soft-point **answers** stay on the IoC façade).
- Parallel frontier scheduling changes (still one ready node per advance).

## Related

- [Transactional durable resume](./transactional-durable-resume.md)
- [Job lane broker](./job-lane-broker.md) (orthogonal: data observe, not dispatch authority)
- OpenAI Dots MH-DOTS-02 via `fangore_insp_effect_revalidation`
