"""Warehouse correlators for graph-run events (OBS-A01..A06).

``GraphExecutor`` merges :func:`graph_trace_context` into every event it emits
so a flat event table can be joined back to the graph, recipe, and authority
that produced each row without opening checkpoints. See
``docs/requirements/event-analytics-schema.md``.

Example::

    >>> from mechaharness.graph import ExecutionGraph
    >>> graph = ExecutionGraph(id="g1", goal="ship")
    >>> graph.template_name, graph.template_version = "verify_repair", "1"
    >>> ctx = graph_trace_context(graph)
    >>> ctx["graph_id"], ctx["recipe_id"], ctx["recipe_version"]
    ('g1', 'verify_repair', '1')
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.events import Event
from mechaharness.graph import ExecutionGraph

#: Keys ``GraphExecutor`` adds to every graph-run event payload (when known).
GRAPH_CORRELATOR_KEYS: tuple[str, ...] = (
    "graph_id",
    "graph_goal",
    "recipe_id",
    "recipe_version",
    "recipe_instance_id",
    "authorization_epoch",
    "live_authorization_epoch",
    "parent_run_id",
    "nest_depth",
)


def graph_trace_context(
    graph: ExecutionGraph,
    *,
    envelope: CapabilityEnvelope | None = None,
    live_authorization_epoch: int | None = None,
    parent_run_id: str | None = None,
    nest_depth: int = 0,
) -> dict[str, Any]:
    """Correlator fields for one graph run; ``None`` values are omitted.

    ``recipe_*`` come from the template stamp on ``graph``. ``authorization_epoch``
    is the envelope's epoch (the authority the run executes under), falling back to
    the graph's stamped epoch; ``live_authorization_epoch`` is the host's live
    source when one is wired.
    """
    epoch = envelope.authorization_epoch if envelope is not None else graph.authorization_epoch
    context: dict[str, Any] = {
        "graph_id": graph.id,
        "graph_goal": graph.goal,
        "recipe_id": graph.template_name,
        "recipe_version": graph.template_version,
        "recipe_instance_id": graph.recipe_instance_id,
        "authorization_epoch": epoch,
        "live_authorization_epoch": live_authorization_epoch,
        "parent_run_id": parent_run_id,
        "nest_depth": nest_depth if parent_run_id is not None else None,
    }
    return {key: value for key, value in context.items() if value is not None}


class NodeAttemptRow(BaseModel):
    """One node attempt projected from ``core:graph_node_start`` / ``_end`` events."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    graph_id: str | None = None
    node_id: str
    kind: str | None = None
    attempt: int = 1
    status: str | None = None
    error: str | None = None
    recipe_id: str | None = None
    recipe_version: str | None = None
    authorization_epoch: int | None = None
    parent_run_id: str | None = None
    started: bool = False
    ended: bool = False


def project_node_attempt_rows(events: Sequence[Event]) -> list[NodeAttemptRow]:
    """Fact rows (one per run/node/attempt) from graph node events, in event order.

    Node-end events that carry no ``attempt`` (early failures such as
    ``no_runner``) attach to the latest open attempt for that node, or become
    their own row.
    """
    rows: dict[tuple[str, str, int], NodeAttemptRow] = {}
    latest: dict[tuple[str, str], int] = {}
    for event in events:
        if event.type not in ("core:graph_node_start", "core:graph_node_end"):
            continue
        payload = event.payload
        node_id = payload.get("node_id")
        if not isinstance(node_id, str):
            continue
        is_start = event.type == "core:graph_node_start"
        raw_attempt = payload.get("attempt")
        if isinstance(raw_attempt, int):
            attempt = raw_attempt
        else:
            attempt = latest.get((event.run_id, node_id), 1)
        key = (event.run_id, node_id, attempt)
        row = rows.get(key)
        if row is None:
            row = NodeAttemptRow(run_id=event.run_id, node_id=node_id, attempt=attempt)
            rows[key] = row
        latest[(event.run_id, node_id)] = attempt
        for field in (
            "graph_id",
            "kind",
            "recipe_id",
            "recipe_version",
            "authorization_epoch",
            "parent_run_id",
        ):
            if payload.get(field) is not None:
                setattr(row, field, payload[field])
        if is_start:
            row.started = True
        else:
            row.ended = True
            row.status = payload.get("status")
            row.error = payload.get("error")
    return list(rows.values())
