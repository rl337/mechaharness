# June host-friction inspiration

June-sourced asks for a more readable MechaHarness host surface and for
**graph-visible** tool loops / nested recipes. This is attribution and product
context, not the normative library contract.

Normative requirements:
[Dynamic tool graph and node components](../requirements/dynamic-tool-graph.md).

Kind catalog:
[Node components](../reference/node-components.md).

Requirements map:
[June host-friction requirements map](./june-host-friction-requirements-map.md).

## Provenance

June documents (host repo, not this tree):

- `docs/requirements/mechaharness-host-friction.md` — HF ledger
- `docs/requirements/mechaharness-dynamic-tool-graph.md` — HF-07 / HF-08
- `docs/requirements/interactive-chat-channels.md` — console blocked on MH

Floor at intake: **mechaharness 0.4.0** (host kit + Agentic Recipes).

## Vocabulary

| Term | Meaning |
|------|---------|
| **Graph node** | Established `GraphNode` in an `ExecutionGraph` |
| **Node component** | Sub-node element that must render **within** its parent graph node |

Node-component kinds are projections of **existing** MechaHarness surfaces
(events, soft points, nest, budget, effects). Do not invent viz-only kinds.

## Ownership

**MechaHarness owns:** graph topology, node-component query + traversal
contract, `host_graph_executor` event tap, Agentic Recipe
`conversational_tool_loop`, recipe-as-tool nest via subgraph.

**June owns:** web console (`WorldGraph` / `GraphViewport`), channel adapters,
Comfy / DocumentStore, product bind of `june.chat`, deletion of parallel
`on_phase` / `imagegen_mirror` paint paths after consuming MH.

## Asks in scope (this pack)

| ID | Topic |
|----|-------|
| HF-05 | Event tap on blessed `host_graph_executor` |
| HF-07 | Dynamic tool-loop as ExecutionGraph / node components |
| HF-08 | Nested recipe-as-tool under `tool_call` |

Already landed in 0.4.0: HF-01 (partial), HF-02, HF-04. Open later: HF-03,
HF-06 (subgraph clone).

## Console consumer bones (June)

Durable path: MH checkpoints / `graph_node_*` → hub → world/scene → continuous
zoom viewport. Temporary debt: soft-lane phase painting and hand-wired
`TappingEventLog` until HF-05/07/08.
