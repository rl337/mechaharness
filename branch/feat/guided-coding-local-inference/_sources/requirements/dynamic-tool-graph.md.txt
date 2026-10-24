# Dynamic tool graph and node components

Normative requirements for graph-visible harness/recipe interiors and the
**node component** contract. Inspiration and AI assistant host provenance:
[ai-assistant-host-friction-inspiration.md](../inspiration/ai-assistant-host-friction-inspiration.md).

Kind catalog (non-normative listing of current kinds):
[Node components](../reference/node-components.md).

## Vocabulary (MUST)

- A **graph node** is a `GraphNode` in an `ExecutionGraph` (including nested
  subgraph children). Graph nodes are scheduled, authorized, checkpointed, and
  resumable.
- A **node component** is a sub-node element that **MUST** declare a
  `parent_node_id` and **MUST** be rendered by hosts **within** that parent
  graph node’s frame. Node components are not free-floating world-graph nodes.
- Documentation and APIs MUST say **graph node** or **node component** — not
  overload “node” for both.

## Kind rule (MUST)

Node-component kinds MUST be projections of concepts that already exist in
MechaHarness (core events, soft points, subgraph nest, stop contracts, budget
levels, effect states, lifecycle `extension_applied`).

MechaHarness MUST NOT mint viz-only component kinds without a corresponding
code surface. When a new executable surface is added, the matching
node-component kind MUST be registered in the same change (see
`.cursor/skills/node-components/SKILL.md`).

## Query (MUST)

MechaHarness MUST provide a query that, given an instantiated graph and/or
template bindings, returns the node components for each graph node for
**pre-layout**. Soft points declared on a recipe MUST appear as `soft_point`
components of the nodes that expose them without a parallel hand list that can
drift.

## Traversal (MUST)

As existing EventLog emits and checkpoints update, hosts MUST be able to align
traversal status with node-component ids (and nested graph node ids) without a
second host-owned observability graph.

## Host tap (HF-05) (MUST)

The blessed host entrypoint (`host_graph_executor` or successor) MUST accept an
injectable `EventLog` (or equivalent tap) so hosts need not hand-wire a dual
executor path for live lighting.

## Conversational tool loop (HF-07) (MUST)

MechaHarness MUST ship Agentic Recipe catalog id `conversational_tool_loop`
whose runtime topology exposes inference and per-tool work as nested graph
nodes and/or node components under a parent tools node, without requiring the
host to pre-unroll `max_iterations` no-op nodes. Bounds MUST use existing
`StopContract` / repeating fields.

## Recipe-as-tool (HF-08) (MUST)

A `tool_call` (graph node or node component) MUST be able to attach a child
`GraphTemplate` / recipe via existing subgraph nest (`child_run_id`, shared
budget). Ordinary function tools remain leaves.

## Non-goals

- Host web console UI
- Channel adapters, media backends, document stores
- Promoting host catalog ids such as `june.chat` into the library catalog
- Pre-unrolled no-op max-turn graph nodes
