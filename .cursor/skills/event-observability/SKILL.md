---
name: event-observability
description: >-
  Keep MechaHarness EventLog emits warehouse-joinable. Use when adding or
  changing CoreEvent types, graph lifecycle emits, GraphExecutor._emit,
  DecisionRecord / TraceEnvelope fields, correlators (graph_id, recipe_id,
  authorization_epoch, parent_run_id), or event-analytics requirements.
---

# Event observability

Events are the only observability substrate. A flat event table must be joinable
to graph, recipe, authority epoch, and run tree **without** opening checkpoints.

Normative: [`docs/requirements/event-analytics-schema.md`](../../../docs/requirements/event-analytics-schema.md)
(OBS-A01..A06). Reference: [`docs/reference/events.md`](../../../docs/reference/events.md).

## When to apply

- Adding a `CoreEvent` subclass or a new `GraphExecutor` emit
- Adding provenance fields to `DecisionRecord` or `TraceEnvelope`
- Stamping new recipe/graph identity that analytics should see
- Writing a projection over events (see `mechaharness.event_correlators`)

## Hard rules

1. **Emit through `GraphExecutor._emit`.** It merges `graph_trace_context` for the
   run; do not hand-copy `graph_id` / `recipe_id` into each payload. Explicit
   payload keys win.
2. **One name per concept.** Reuse correlator names exactly (`graph_id`,
   `recipe_id`, `recipe_version`, `authorization_epoch`, `parent_run_id`,
   `nest_depth`); `DecisionRecord` / `TraceEnvelope` use the same names.
3. **Open payloads.** Hosts add `acme:`-namespaced keys; never `extra="forbid"`.
4. **No parallel bus.** Do not add a second event type system, warehouse writer, or
   analytics registry to this package (`.cursor/rules/host-extend.mdc`).
5. **Facts hold keys, dims hold text.** New descriptive fields go on a dimension
   in the schema doc, not repeated per fact row.

## Workflow

```text
Observability change:
- [ ] 1. New correlator? Add to graph_trace_context + GRAPH_CORRELATOR_KEYS
- [ ] 2. Mirror on DecisionRecord / TraceEnvelope when it is a shared dimension
- [ ] 3. Update docs/requirements/event-analytics-schema.md (OBS-A* + fact/dim table)
- [ ] 4. Update docs/reference/events.md "Required correlators"
- [ ] 5. Extend nubble_graph_event_correlators (or add a story) — regenerate guide
- [ ] 6. pytest tests/test_event_correlators.py tests/stories
```

## Anti-patterns

```text
# BAD — payload["recipe"] = name in one emit, "recipe_id" in another
# BAD — loading core:graph_node checkpoint events as analytics facts
# BAD — recipe description text repeated on every node-attempt row
# BAD — a host-specific warehouse writer inside src/mechaharness
```

## Related

- [`user-stories`](../user-stories/SKILL.md) — stories that cover OBS-* ids
- [`project-docs`](../project-docs/SKILL.md) — requirements/reference doc layout
- [`node-components`](../node-components/SKILL.md) — events that light node components
