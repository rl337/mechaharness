"""Node components — sub-node elements that render within a graph node.

Kinds are projections of existing MechaHarness surfaces (core events, soft
points, subgraph nest, stop contracts, budget, effects). Do not invent
viz-only kinds.

See ``docs/reference/node-components.md`` and
``docs/requirements/dynamic-tool-graph.md``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.graph_templates.base import GraphTemplate, SoftPoint

NodeComponentKind = Literal[
    "turn_start",
    "inference",
    "tool_call",
    "tool_result",
    "max_turns",
    "cost",
    "access_check",
    "extension_applied",
    "soft_point",
    "child_graph",
    "stop_contract",
    "budget_level",
    "effect_state",
]

NODE_COMPONENT_KINDS: frozenset[str] = frozenset(
    {
        "turn_start",
        "inference",
        "tool_call",
        "tool_result",
        "max_turns",
        "cost",
        "access_check",
        "extension_applied",
        "soft_point",
        "child_graph",
        "stop_contract",
        "budget_level",
        "effect_state",
    }
)

# Event type suffixes / keys → component kind (closed inventory).
_EVENT_KIND_MAP: dict[str, NodeComponentKind] = {
    "turn_start": "turn_start",
    "inference": "inference",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "max_turns": "max_turns",
    "cost": "cost",
    "access_check": "access_check",
    "extension_applied": "extension_applied",
}


class NodeComponent(BaseModel):
    """One sub-node element scoped to a parent graph node."""

    model_config = ConfigDict(extra="allow")

    id: str
    kind: NodeComponentKind
    parent_node_id: str
    label: str = ""
    executable: bool = True
    visualizable: bool = True
    soft_point_name: str | None = None
    soft_point_kind: str | None = None
    tool_name: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class TraversalRecord(BaseModel):
    """Live status for a graph node or node component."""

    model_config = ConfigDict(extra="allow")

    id: str
    kind: str
    parent_node_id: str | None = None
    status: str | None = None
    execution_node_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


def _has_subgraph(node: GraphNode) -> bool:
    if node.subgraph:
        return True
    raw = node.payload.get("subgraph")
    return isinstance(raw, dict)


def _components_for_node(node: GraphNode) -> list[NodeComponent]:
    comps: list[NodeComponent] = []
    nid = node.id
    if node.repeating or node.stop_contract:
        comps.append(
            NodeComponent(
                id=f"{nid}/stop_contract",
                kind="stop_contract",
                parent_node_id=nid,
                label="stop_contract",
                executable=False,
                detail={"repeating": node.repeating, "stop_contract": node.stop_contract},
            )
        )
    if _has_subgraph(node) or node.payload.get("child_run_id"):
        comps.append(
            NodeComponent(
                id=f"{nid}/child_graph",
                kind="child_graph",
                parent_node_id=nid,
                label="child_graph",
                detail={
                    "child_run_id": node.payload.get("child_run_id"),
                    "child_graph_id": node.payload.get("child_graph_id"),
                },
            )
        )
    if node.payload.get("requires_effect_reconciliation") or node.payload.get(
        "effect_state"
    ):
        comps.append(
            NodeComponent(
                id=f"{nid}/effect_state",
                kind="effect_state",
                parent_node_id=nid,
                label="effect_state",
                detail={
                    "effect_state": node.payload.get("effect_state"),
                    "requires_effect_reconciliation": node.payload.get(
                        "requires_effect_reconciliation"
                    ),
                },
            )
        )
    if node.payload.get("soft_point") or node.payload.get("firmness") == "soft":
        name = str(node.payload.get("soft_point") or node.id)
        comps.append(
            NodeComponent(
                id=f"{nid}/soft_point:{name}",
                kind="soft_point",
                parent_node_id=nid,
                label=name,
                executable=False,
                soft_point_name=name,
            )
        )
    if node.payload.get("budget_level") is not None:
        comps.append(
            NodeComponent(
                id=f"{nid}/budget_level",
                kind="budget_level",
                parent_node_id=nid,
                label="budget_level",
                executable=False,
                detail={"budget_level": node.payload.get("budget_level")},
            )
        )
    return comps


def _soft_point_components(
    graph: ExecutionGraph,
    soft_points: Sequence[SoftPoint],
) -> list[NodeComponent]:
    """Attach template soft points to graph nodes (prefer payload match)."""
    if not soft_points or not graph.nodes:
        return []
    node_ids = list(graph.nodes)
    default_parent = node_ids[0]
    comps: list[NodeComponent] = []
    for sp in soft_points:
        parent = default_parent
        for nid, node in graph.nodes.items():
            blob = f"{nid} {node.kind} {node.goal} {node.payload}"
            if sp.name in blob:
                parent = nid
                break
        comps.append(
            NodeComponent(
                id=f"{parent}/soft_point:{sp.name}",
                kind="soft_point",
                parent_node_id=parent,
                label=sp.name,
                executable=False,
                soft_point_name=sp.name,
                soft_point_kind=sp.kind,
                detail={"required": sp.required, "description": sp.description},
            )
        )
    return comps


def node_components_for(
    graph: ExecutionGraph,
    *,
    template: GraphTemplate | None = None,
    soft_points: Sequence[SoftPoint] | None = None,
    tool_names: Sequence[str] | None = None,
    tools_parent_id: str | None = None,
) -> list[NodeComponent]:
    """Derive node components from an instantiated graph and optional binds.

    Soft points come from ``template.soft_points`` or ``soft_points=``. Tool
    names become planned ``tool_call`` components under ``tools_parent_id``
    (default: first node with kind ``conversational_tool_loop`` or ``tools``,
    else first node).
    """
    comps: list[NodeComponent] = []
    seen: set[str] = set()

    def _add(c: NodeComponent) -> None:
        if c.id not in seen:
            if c.kind not in NODE_COMPONENT_KINDS:
                raise ValueError(f"unknown node component kind: {c.kind!r}")
            if not c.parent_node_id:
                raise ValueError(f"node component {c.id!r} missing parent_node_id")
            seen.add(c.id)
            comps.append(c)

    for node in graph.nodes.values():
        for c in _components_for_node(node):
            _add(c)

    sps = list(soft_points) if soft_points is not None else []
    if template is not None:
        sps = list(template.soft_points)
    for c in _soft_point_components(graph, sps):
        _add(c)

    if tool_names:
        parent = tools_parent_id
        if parent is None:
            for nid, node in graph.nodes.items():
                if node.kind in {"conversational_tool_loop", "tools"} or nid.endswith(
                    "/tools"
                ):
                    parent = nid
                    break
            if parent is None and graph.nodes:
                parent = next(iter(graph.nodes))
        if parent is not None:
            for name in tool_names:
                _add(
                    NodeComponent(
                        id=f"{parent}/tool_call:{name}",
                        kind="tool_call",
                        parent_node_id=parent,
                        label=name,
                        tool_name=str(name),
                    )
                )
            _add(
                NodeComponent(
                    id=f"{parent}/inference",
                    kind="inference",
                    parent_node_id=parent,
                    label="inference",
                )
            )
            _add(
                NodeComponent(
                    id=f"{parent}/turn_start",
                    kind="turn_start",
                    parent_node_id=parent,
                    label="turn_start",
                    executable=False,
                )
            )

    return comps


def node_components_for_harness(
    *,
    parent_node_id: str,
    tool_names: Sequence[str] | None = None,
    include_turn: bool = True,
    include_inference: bool = True,
) -> list[NodeComponent]:
    """Planned harness-interior components under a containing graph node."""
    comps: list[NodeComponent] = []
    if include_turn:
        comps.append(
            NodeComponent(
                id=f"{parent_node_id}/turn_start",
                kind="turn_start",
                parent_node_id=parent_node_id,
                label="turn_start",
                executable=False,
            )
        )
    if include_inference:
        comps.append(
            NodeComponent(
                id=f"{parent_node_id}/inference",
                kind="inference",
                parent_node_id=parent_node_id,
                label="inference",
            )
        )
    for name in tool_names or ():
        comps.append(
            NodeComponent(
                id=f"{parent_node_id}/tool_call:{name}",
                kind="tool_call",
                parent_node_id=parent_node_id,
                label=str(name),
                tool_name=str(name),
            )
        )
        comps.append(
            NodeComponent(
                id=f"{parent_node_id}/tool_result:{name}",
                kind="tool_result",
                parent_node_id=parent_node_id,
                label=str(name),
                tool_name=str(name),
            )
        )
    return comps


def _event_type_suffix(etype: str) -> str:
    if ":" in etype:
        return etype.rsplit(":", 1)[-1]
    return etype


def traversal_from_events(
    events: Sequence[Mapping[str, Any] | Any],
    *,
    default_parent_node_id: str | None = None,
) -> list[TraversalRecord]:
    """Project EventLog-like payloads into component-aligned traversal records."""
    records: list[TraversalRecord] = []
    for idx, event in enumerate(events):
        if hasattr(event, "type"):
            etype = str(getattr(event, "type", "") or "")
            payload = dict(getattr(event, "payload", None) or {})
        else:
            etype = str(event.get("type") or event.get("event_type") or "")
            payload = dict(event.get("payload") or {})
        suffix = _event_type_suffix(etype)
        kind = _EVENT_KIND_MAP.get(suffix)
        if kind is None:
            continue
        parent = (
            payload.get("parent_node_id")
            or payload.get("execution_node_id")
            or payload.get("graph_node_id")
            or default_parent_node_id
        )
        parent_s = str(parent) if parent else None
        comp_id = payload.get("component_id") or payload.get("node_id")
        if not comp_id:
            tool = payload.get("tool_name") or payload.get("name")
            if tool and parent_s:
                comp_id = f"{parent_s}/{kind}:{tool}"
            elif parent_s:
                comp_id = f"{parent_s}/{kind}"
            else:
                comp_id = f"evt-{idx}:{kind}"
        records.append(
            TraversalRecord(
                id=str(comp_id),
                kind=kind,
                parent_node_id=parent_s,
                status=str(payload["status"]) if payload.get("status") else None,
                execution_node_id=(
                    str(payload["execution_node_id"])
                    if payload.get("execution_node_id")
                    else parent_s
                ),
                detail=payload,
            )
        )
    return records


def embed_recipe_as_tool(
    child: ExecutionGraph,
    *,
    parent_node_id: str,
    tool_name: str | None = None,
) -> GraphNode:
    """Attach a child recipe under a tool_call graph node (HF-08).

    Uses the same nest shape as :class:`SubgraphNodeRunner.embed` so
    ``GraphExecutor`` runs the child with ``child_run_id`` and shared budget.
    """
    from mechaharness.graph_templates.base import SubgraphNodeRunner

    node = SubgraphNodeRunner.embed(child, parent_node_id=parent_node_id)
    node.kind = "tool_call"
    node.payload = {
        **node.payload,
        "tool_name": tool_name or parent_node_id,
        "recipe_as_tool": True,
        "template_name": child.template_name,
    }
    return node


__all__ = [
    "NODE_COMPONENT_KINDS",
    "NodeComponent",
    "NodeComponentKind",
    "TraversalRecord",
    "embed_recipe_as_tool",
    "node_components_for",
    "node_components_for_harness",
    "traversal_from_events",
]
