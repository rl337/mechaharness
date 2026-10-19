"""Graph-run correlators and node-attempt projection (OBS-A01..A06)."""

from __future__ import annotations

from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.events import Event
from mechaharness.event_correlators import (
    GRAPH_CORRELATOR_KEYS,
    graph_trace_context,
    project_node_attempt_rows,
)
from mechaharness.graph import ExecutionGraph


def test_context_omits_absent_values_and_prefers_envelope_epoch() -> None:
    graph = ExecutionGraph(id="g1", goal="ship", authorization_epoch=1)
    bare = graph_trace_context(graph)
    assert bare == {"graph_id": "g1", "graph_goal": "ship", "authorization_epoch": 1}

    graph.template_name, graph.template_version = "verify_repair", "2"
    ctx = graph_trace_context(
        graph,
        envelope=CapabilityEnvelope(authorization_epoch=5),
        live_authorization_epoch=6,
        parent_run_id="parent",
        nest_depth=2,
    )
    assert ctx["recipe_id"] == "verify_repair"
    assert ctx["recipe_version"] == "2"
    assert ctx["authorization_epoch"] == 5
    assert ctx["live_authorization_epoch"] == 6
    assert (ctx["parent_run_id"], ctx["nest_depth"]) == ("parent", 2)
    assert set(ctx) <= set(GRAPH_CORRELATOR_KEYS)


def _event(name: str, /, **payload: object) -> Event:
    return Event(type=f"core:{name}", agent_id="a", run_id="r", payload=dict(payload))


def test_projection_pairs_start_end_and_handles_early_failure() -> None:
    rows = project_node_attempt_rows(
        [
            _event("graph_start", goal="x"),
            _event("graph_node_start", node_id="a", kind="k", attempt=1, graph_id="g"),
            _event("graph_node_end", node_id="a", kind="k", attempt=1, status="failed", error="e"),
            _event("graph_node_start", node_id="a", kind="k", attempt=2),
            _event("graph_node_end", node_id="a", kind="k", attempt=2, status="succeeded"),
            _event("graph_node_end", node_id="b", status="failed", error="no_runner"),
        ]
    )
    assert [(r.node_id, r.attempt, r.status, r.started, r.ended) for r in rows] == [
        ("a", 1, "failed", True, True),
        ("a", 2, "succeeded", True, True),
        ("b", 1, "failed", False, True),
    ]
    assert rows[0].graph_id == "g"
    assert rows[0].error == "e"
