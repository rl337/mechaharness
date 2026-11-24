# AI assistant project host-friction inspiration

Asks from an **AI assistant** host for a more readable MechaHarness host surface
and for **graph-visible** tool loops / nested recipes. This is attribution and
product context, not the normative library contract.

Do not name or link private host repositories from this tree.

Normative requirements:
[Dynamic tool graph and node components](../requirements/dynamic-tool-graph.md).

Kind catalog:
[Node components](../reference/node-components.md).

Requirements map:
[AI assistant host-friction requirements map](./ai-assistant-host-friction-requirements-map.md).

## Provenance

Host documents (private; summarized here, not linked):

- Host-friction ledger (`HF-*` ids)
- Dynamic tool-graph requirements for conversational loops / recipe-as-tool
- Interactive chat / console requirements blocked on MechaHarness surfaces

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

**AI assistant host owns:** web console (world / viewport), channel adapters,
media / document backends, product bind of chat surfaces, deletion of parallel
phase / mirror paint paths after consuming MechaHarness.

## Asks in scope (this pack)

| ID | Topic |
|----|-------|
| HF-05 | Event tap on blessed `host_graph_executor` |
| HF-07 | Dynamic tool-loop as ExecutionGraph / node components |
| HF-08 | Nested recipe-as-tool under `tool_call` |

Already landed in 0.4.0: HF-01 (partial), HF-02, HF-04. Open later: HF-03,
HF-06 (subgraph clone).

## Console consumer bones (host)

Durable path: MechaHarness checkpoints / `graph_node_*` → hub → world/scene →
continuous zoom viewport. Temporary debt: soft-lane phase painting and
hand-wired event taps until HF-05/07/08.
