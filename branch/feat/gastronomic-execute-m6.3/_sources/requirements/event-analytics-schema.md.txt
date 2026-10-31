# Event analytics schema requirements

## Motivation

`EventLog` is the observability substrate (`docs/reference/events.md`). Hosts load
those events — plus `DecisionRecord` lines and `TraceEnvelope` provenance — into a
warehouse and need to answer questions like "which recipe version denied the most
sends under epoch 3?" **without** opening checkpoints or replaying transcripts.

This page is the contract between MechaHarness emitters and a warehouse
consumer. It specifies the correlator fields every graph-run event carries and a
near-3NF fact/dimension decomposition. It does not mandate a warehouse product,
table DDL, or a second event bus: the substrate stays `Event` / `EventLog`.

## Ownership boundary

MechaHarness owns:

- stable correlator field names on `core:graph_*` lifecycle events;
- field-name parity across `DecisionRecord`, `TraceEnvelope`, and graph events;
- `project_node_attempt_rows` as a reference projection of the node-attempt fact.

Hosts own:

- warehouse DDL, partitioning, retention, and PII handling;
- host-namespaced correlators (`acme:ticket_id`) added to `payload`;
- any join to business entities.

## Requirements

### OBS-A01: Graph identity on every graph lifecycle event

`core:graph_start`, `core:graph_end`, `core:graph_node_start`, and
`core:graph_node_end` emitted by `GraphExecutor` MUST carry `graph_id` and
`graph_goal` in `payload`, in addition to the envelope's `run_id` and `agent_id`.
Explicit payload keys MUST win over correlators on collision.

### OBS-A02: Recipe identity from the template stamp

When the graph is stamped by an Agentic Recipe, the same events MUST carry
`recipe_id` (the catalog id, `ExecutionGraph.template_name`) and `recipe_version`
(`template_version`), and SHOULD carry `recipe_instance_id`. Unstamped graphs omit
these keys; consumers MUST treat absence as "pure tiling container", not an error.

### OBS-A03: Authorization epoch

Graph lifecycle events MUST carry `authorization_epoch` — the epoch of the
`CapabilityEnvelope` the run executes under (falling back to the graph's stamped
epoch). When the host wires `executor.live_authorization_epoch`, events SHOULD also
carry `live_authorization_epoch` so a revoked-then-resumed run is visible in the
warehouse.

### OBS-A04: Nesting

Events from a nested subgraph run MUST carry `parent_run_id` and `nest_depth`
(1 for a direct child). The parent's `core:graph_node_end` for the embedding node
carries `child_run_id`, so the run tree is reconstructable from either direction.

### OBS-A05: Node-attempt fact

One row per `(run_id, node_id, attempt)` MUST be derivable from node start/end
events alone. `node_id`, `kind`, `attempt`, and `status` are payload fields of
`core:graph_node_start` / `core:graph_node_end`. `project_node_attempt_rows`
(`mechaharness.event_correlators`) is the reference projection.

### OBS-A06: Decision and trace alignment

`DecisionRecord` and `TraceEnvelope` MUST use the same names as the graph
correlators for shared dimensions: `run_id`, `node_id`, `graph_id`, `recipe_id`,
`recipe_version`, `authorization_epoch` (`DecisionRecord` also `parent_run_id`).
A decision row joins to a node-attempt row on `(run_id, node_id)` and to the
recipe dimension on `(recipe_id, recipe_version)` with no string parsing.

## Fact / dimension decomposition

Facts hold events and measures; dimensions hold slowly-changing descriptors keyed
by the correlators above. Each non-key column depends on the key only.

| Table | Grain | Key | Source |
|-------|-------|-----|--------|
| `fact_graph_run` | one graph run | `run_id` | `core:graph_start` / `core:graph_end` |
| `fact_node_attempt` | one node attempt | `run_id, node_id, attempt` | `core:graph_node_start` / `_end` (`project_node_attempt_rows`) |
| `fact_decision` | one decision | `event_id` | `core:decision` / `DecisionRecord` |
| `fact_effect` | one external effect | `effect_id` | `core:graph_node_end` effect fields, effect ledger |
| `dim_graph` | graph definition | `graph_id` | `graph_id`, `graph_goal` |
| `dim_recipe` | recipe version | `recipe_id, recipe_version` | template stamp |
| `dim_authority_epoch` | authority epoch | `authorization_epoch` | `CapabilityEnvelope` |
| `dim_run_tree` | parent/child edge | `run_id` | `parent_run_id`, `nest_depth` |

`fact_graph_run` stores only keys (`graph_id`, `recipe_*`, `authorization_epoch`,
`parent_run_id`) plus run measures (status, node count, budget spent); descriptive
text such as `graph_goal` belongs on `dim_graph`.

## Scope notes

- Checkpoint events (`core:graph_node`) carry the full graph snapshot, not
  correlators; warehouses SHOULD NOT load them as facts.
- `core:access_check` and `core:extension_applied` are emitted by their owners and
  join on `run_id` only.

## Acceptance

- Story `nubble_graph_event_correlators` (multi-node graph with a nested subgraph).
- Unit: `tests/test_event_correlators.py`.
