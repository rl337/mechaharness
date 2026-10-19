---
name: mechaharness-observability
description: >-
  Wires MechaHarness EventLog streams into host warehouses and consoles with
  joinable correlators (graph_id, recipe_id/version, authorization_epoch,
  nest parent_run_id). Use when loading events into SQL/BI, building run UIs,
  or adding DecisionRecord / TraceEnvelope fields in a host app.
---

# MechaHarness observability (host side)

MechaHarness owns the **emit contract**. Your host owns the **warehouse, ETL,
and UI**. Prefer richer scalar/id correlators so SQL can reconstruct graph
decision-making without replaying opaque blobs.

Contract: `docs/requirements/event-analytics-schema.md` (OBS-A01..A06).
Reference: `docs/reference/events.md`.

## Join keys to expect

On `core:graph_*` lifecycle events (and aligned decision/trace records):

| Key | Role |
|-----|------|
| `run_id` / `agent_id` | run identity (envelope) |
| `graph_id` / `graph_goal` | graph fact |
| `node_id` / `node_kind` / `attempt` | node attempt |
| `recipe_id` / `recipe_version` | recipe dimension |
| `authorization_epoch` | authority dimension |
| `parent_run_id` / nest depth | nested run lineage |
| `decision_id` / `verdict` / `effect_id` | when present |

```python
from mechaharness.host_apis import (
    GRAPH_CORRELATOR_KEYS,
    project_node_attempt_rows,
)

# Reference projector: event list → node-attempt rows (no warehouse required)
rows = project_node_attempt_rows(events)
```

## Do

1. Persist the event stream as the source of truth for analytics; do not
   require replaying every observational event for durable resume.
2. Map emits to fact families (`fact_node_attempt`, `fact_decision`,
   `fact_effect`, …) in your warehouse DDL.
3. Add host keys under your namespace (`june:ticket_id`) in open `payload`.
4. Prefer scalar / enum / short string attributes; store large objects in a
   side table keyed by a stable id.

## Don't

1. Strip correlators “to reduce noise” — filter in the warehouse instead.
2. Embed secrets, raw credentials, or unbounded chat transcripts in facts.
3. Invent a second event bus inside MechaHarness; consume `EventLog`.
4. Rename or remove correlator keys without treating it as a breaking
   analytics change (coordinate with upstream CHANGELOG).

## See also

- Host integration: companion skill `use-mechaharness`
- Requirements: `docs/requirements/event-analytics-schema.md`
- Site events reference: https://rl337.org/mechaharness/reference/events.html
