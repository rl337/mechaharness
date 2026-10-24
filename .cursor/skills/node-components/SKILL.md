---
name: node-components
description: >-
  Declare and derive MechaHarness node components (sub-node elements that
  render within a graph node) from existing events, soft points, nest, budget,
  and effects. Use when adding CoreEvent types, soft points, effectful runners,
  harness emits, Agentic Recipes, graph node kinds, traversal/viz contracts,
  or host console lighting.
---

# Node components

A **graph node** is a `GraphNode` in an `ExecutionGraph`. A **node component**
is a sub-node element that **must** have `parent_node_id` and **must** render
inside that parent’s frame. Hosts (e.g. the AI assistant host console) pre-layout from query and
light up from traversal.

Normative:
[`docs/requirements/dynamic-tool-graph.md`](../../../docs/requirements/dynamic-tool-graph.md).

Catalog:
[`docs/reference/node-components.md`](../../../docs/reference/node-components.md).

## When to apply

- Adding or changing `CoreEvent` / lifecycle emits
- Adding `SoftPoint` / `SoftPointKind` values
- Effectful runners / `EffectState` surfaces
- Harness loop emits (`inference`, `tool_call`, …)
- New or changed Agentic Recipes / graph templates
- Traversal, RolloutGraph links, host kit event tap
- Docs or stories about console zoom / path lighting

## Hard rules

1. **Kinds ⊆ code surfaces.** Do not invent viz-only component kinds.
2. **Parent required.** Every component has `parent_node_id`.
3. **Derive, don’t drift.** Prefer `node_components_for(graph)` from soft points,
   repeating/stop_contract, subgraph embeds, tool binds — not a parallel list.
4. **New surface ⇒ same change.** New event/model first, then register kind in
   `node_component` catalog + reference doc + tests/story as needed.
5. **Nested recipes are graph nodes.** Parent may expose `child_graph` handle
   component; child interiors are components of child nodes.

## Procedure

```text
Node-component task:
- [ ] 1. Identify parent graph node id(s)
- [ ] 2. Map work to an existing kind in docs/reference/node-components.md
- [ ] 3. If no kind fits: add the executable surface (event/field/soft point)
        in this PR, then add the kind to NODE_COMPONENT_KINDS + reference doc
- [ ] 4. Ensure query derivation picks it up (soft point / nest / stop / …)
- [ ] 5. Ensure traversal/events carry parent + component id alignment
- [ ] 6. Recipe ref "Node components" subsection / story implementation names kinds
```

## Anti-patterns

```text
# BAD — component kind "llm_sparkle" with no CoreEvent or SoftPoint
# BAD — components at world root with no parent_node_id
# BAD — hand-maintained component lists that ignore SoftPoint declarations
# BAD — calling a nested GraphNode a "component"

# GOOD — soft_point from template.soft_points
# GOOD — tool_call / inference from existing core events
# GOOD — child_graph handle on subgraph parent; child nodes own their components
```

## Related

- [`agentic-recipes`](../agentic-recipes/SKILL.md)
- [`user-stories`](../user-stories/SKILL.md)
- [`project-docs`](../project-docs/SKILL.md)
- `mechaharness.node_component`
