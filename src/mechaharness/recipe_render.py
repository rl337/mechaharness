"""Render an Agentic Recipe as an execution-flow diagram + explanations.

The diagram is a pure-Python SVG layout (`recipe_diagram`): top-level edges are
recipe execution order (prepare → harness_loop → render). Loop/nest nodes are
**titled round containers** whose title is the graph node name; interiors use
start/end circles and ``then`` edges, packed about three steps per row.

Configuration soft points render as **ER-style tables** (name / type / value)
on leaf nodes. Long pydoc lives *below* the drawing.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.graph_templates.base import GraphTemplate, GraphTemplateParams
from mechaharness.node_component import (
    NodeComponent,
    node_components_for,
    node_components_for_harness,
)
from mechaharness.recipe_diagram import (
    EdgeSpec,
    FieldRow,
    NodeSpec,
    StepSpec,
    build_recipe_svg,
)
from mechaharness.recipe_runner import get_recipe, resolve_registry

# Closed kind catalog prose (mirrors docs/reference/node-components.md).
_COMPONENT_KIND_DOCS: dict[str, str] = {
    "turn_start": "Harness turn boundary (`core:turn_start`).",
    "inference": "Model complete step (`core:inference`).",
    "tool_call": "One tool invocation (`core:tool_call`).",
    "tool_result": "Tool outcome (`core:tool_result`).",
    "max_turns": "Turn ceiling hit (`core:max_turns`).",
    "cost": "Priced spend span (`core:cost`).",
    "access_check": "Grant allow/deny (`core:access_check`).",
    "extension_applied": "Lifecycle extension fired (`core:extension_applied`).",
    "soft_point": (
        "Host-binding slot declared on the Agentic Recipe "
        "(`SoftPoint` / SoftPointKind)."
    ),
    "child_graph": "Handle to a nested ExecutionGraph (`subgraph` / child_run_id).",
    "stop_contract": "Expandable / bound loop marker (`repeating` + StopContract).",
    "budget_level": "Shared budget ledger level (OK / soft / hard).",
    "effect_state": "Effectful node external lifecycle (`EffectState`).",
}

class RecipeRender(BaseModel):
    """Fully rendered recipe graph plus out-of-band explanations."""

    model_config = ConfigDict(extra="allow")

    recipe: str
    version: str = "1"
    summary: str = ""
    svg: str
    explanations_markdown: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    components: list[dict[str, Any]] = Field(default_factory=list)
    fields_by_node: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


def _cell(text: Any) -> str:
    """Sanitize a display cell (tables / titles)."""
    s = str(text).replace("|", "/").replace("\n", " ").replace("`", "'")
    return s if s else "—"


def _is_config_soft_point(comp: NodeComponent) -> bool:
    if comp.kind != "soft_point":
        return False
    kind = comp.soft_point_kind or str(comp.detail.get("soft_point_kind") or "other")
    return kind != "tool"


def _is_nest_component(comp: NodeComponent) -> bool:
    return comp.kind == "child_graph"


def _node_is_nest(node: GraphNode, comps: Sequence[NodeComponent]) -> bool:
    if node.subgraph or node.payload.get("child_run_id"):
        return True
    return any(_is_nest_component(c) for c in comps)


def _field_value(
    name: str,
    *,
    template: GraphTemplate,
    params: GraphTemplateParams,
    detail: Mapping[str, Any] | None = None,
) -> Any:
    if name in params.soft_bindings:
        return params.soft_bindings[name]
    if name in params.inputs:
        return params.inputs[name]
    for point in template.soft_points:
        if point.name == name and point.default is not None:
            return point.default
    if detail and detail.get("default") is not None:
        return detail["default"]
    return "—"


def _partition_components(
    components: Sequence[NodeComponent],
) -> tuple[dict[str, list[NodeComponent]], dict[str, list[NodeComponent]]]:
    fields: dict[str, list[NodeComponent]] = defaultdict(list)
    shapes: dict[str, list[NodeComponent]] = defaultdict(list)
    for comp in components:
        if _is_config_soft_point(comp):
            fields[comp.parent_node_id].append(comp)
        else:
            shapes[comp.parent_node_id].append(comp)
    return fields, shapes


def _ordered_flow_comps(comps: Sequence[NodeComponent]) -> list[NodeComponent]:
    """Order harness/tool interiors as execution sequence, not a fan-out tree."""
    turns = [c for c in comps if c.kind == "turn_start"]
    inferences = [c for c in comps if c.kind == "inference"]
    paired: list[NodeComponent] = []
    used_results: set[str] = set()
    for call in (c for c in comps if c.kind == "tool_call"):
        paired.append(call)
        for result in comps:
            if (
                result.kind == "tool_result"
                and result.tool_name == call.tool_name
                and result.id not in used_results
            ):
                paired.append(result)
                used_results.add(result.id)
                break
    orphan_results = [
        c for c in comps if c.kind == "tool_result" and c.id not in used_results
    ]
    handled = {c.id for c in turns + inferences + paired + orphan_results}
    other = [
        c
        for c in comps
        if c.id not in handled
        and c.kind
        in {"stop_contract", "child_graph", "effect_state", "budget_level"}
    ]
    return turns + inferences + paired + orphan_results + other


def _default_params(
    template: GraphTemplate,
    *,
    soft_bindings: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    goal: str | None = None,
) -> GraphTemplateParams:
    soft = dict(soft_bindings or {})
    for point in template.soft_points:
        if point.required and point.name not in soft and point.default is None:
            soft[point.name] = f"<{point.name}>"
    branch_payloads: list[dict[str, Any]] = []
    if template.name in {"fan_out_aggregate", "independent_review"}:
        branch_payloads = [{"index": 0}, {"index": 1}]
    acceptance: list[str] = []
    if template.name in {"verify_repair", "fan_out_aggregate", "independent_review"}:
        acceptance = ["render_preview"]
    return GraphTemplateParams(
        goal=goal or f"render:{template.name}",
        soft_bindings=soft,
        inputs=dict(inputs or {}),
        branch_payloads=branch_payloads,
        acceptance=acceptance,
    )


def _edge_pairs(graph: ExecutionGraph) -> list[tuple[str, str, str]]:
    pairs: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for edge in graph.edges:
        key = (edge.from_node, edge.to_node)
        if key in seen:
            continue
        seen.add(key)
        reason = edge.reason or ",".join(edge.types) or "depends"
        pairs.append((edge.from_node, edge.to_node, reason))
    for node in graph.nodes.values():
        for dep in node.depends_on:
            key = (dep, node.id)
            if key in seen:
                continue
            seen.add(key)
            pairs.append((dep, node.id, "depends_on"))
    return pairs


def _node_blurb(node: GraphNode) -> str:
    bits = [f"kind=`{node.kind}`"]
    if node.goal:
        bits.append(f"goal: {node.goal}")
    if node.repeating:
        bits.append("repeating")
    if node.stop_contract:
        bits.append("has stop_contract")
    if node.subgraph or node.payload.get("child_run_id"):
        bits.append("nests child_graph")
    return "; ".join(bits)


def _component_blurb(comp: NodeComponent, template: GraphTemplate | None) -> str:
    lines = [_COMPONENT_KIND_DOCS.get(comp.kind, f"Node component kind `{comp.kind}`.")]
    if comp.soft_point_name and template is not None:
        for point in template.soft_points:
            if point.name == comp.soft_point_name:
                if point.description:
                    lines.append(point.description)
                lines.append(
                    f"SoftPointKind=`{point.kind}`; required={point.required}."
                )
                if point.default is not None:
                    lines.append(f"Default: `{point.default!r}`.")
                break
    elif comp.detail.get("description"):
        lines.append(str(comp.detail["description"]))
    if comp.tool_name:
        lines.append(f"Planned tool: `{comp.tool_name}`.")
    if comp.label and comp.label not in {comp.kind, comp.soft_point_name, comp.tool_name}:
        lines.append(f"Label: {comp.label}.")
    return " ".join(lines)


def _comp_plain_label(comp: NodeComponent) -> str:
    if comp.tool_name and comp.kind in {"tool_call", "tool_result"}:
        return f"{comp.kind}:{comp.tool_name}"
    if comp.soft_point_name:
        return f"soft_point:{comp.soft_point_name}"
    return comp.label or comp.kind


def _container_title(
    nid: str,
    node: GraphNode,
    field_comps: Sequence[NodeComponent],
    *,
    template: GraphTemplate,
    params: GraphTemplateParams,
) -> str:
    title = f"{nid} · {node.kind}"
    if node.goal:
        title = f"{title}: {node.goal}"
    if field_comps:
        bits = []
        for comp in field_comps[:4]:
            name = comp.soft_point_name or comp.label
            value = _field_value(
                name, template=template, params=params, detail=comp.detail
            )
            bits.append(f"{name}={value}")
        if len(field_comps) > 4:
            bits.append("…")
        title = f"{title} ({', '.join(bits)})"
    return _cell(title)


def build_svg(
    graph: ExecutionGraph,
    components: Sequence[NodeComponent],
    *,
    title: str,
    template: GraphTemplate,
    params: GraphTemplateParams,
) -> str:
    """Execution flow SVG: ER tables; loop bodies inside a titled container."""
    fields_by, shapes_by = _partition_components(components)
    specs: list[NodeSpec] = []

    for nid, node in graph.nodes.items():
        field_comps = fields_by.get(nid) or []
        shape_comps = _ordered_flow_comps(shapes_by.get(nid) or [])

        if shape_comps:
            steps = [StepSpec(id=f"{nid}/start", label="start", kind="circle")]
            for comp in shape_comps:
                steps.append(
                    StepSpec(
                        id=comp.id,
                        label=_comp_plain_label(comp),
                        kind="round" if _is_nest_component(comp) else "rect",
                    )
                )
            steps.append(StepSpec(id=f"{nid}/end", label="end", kind="circle"))
            specs.append(
                NodeSpec(
                    id=nid,
                    kind=node.kind,
                    title=_container_title(
                        nid, node, field_comps, template=template, params=params
                    ),
                    steps=steps,
                )
            )
            continue

        fields = [
            FieldRow(
                name=_cell(c.soft_point_name or c.label or c.id),
                type=_cell(c.soft_point_kind or "other"),
                value=_cell(
                    _field_value(
                        c.soft_point_name or c.label or c.id,
                        template=template,
                        params=params,
                        detail=c.detail,
                    )
                ),
            )
            for c in field_comps
        ]
        node_title = f"{nid} · {node.kind}"
        subtitle = _cell(node.goal) if node.goal else ""
        if fields:
            specs.append(
                NodeSpec(
                    id=nid,
                    kind=node.kind,
                    title=_cell(node_title),
                    subtitle=subtitle,
                    fields=fields,
                )
            )
        else:
            plain = node_title
            if node.goal:
                plain = f"{plain}: {node.goal}"
            specs.append(
                NodeSpec(id=nid, kind=node.kind, title=_cell(plain))
            )

    edges = [
        EdgeSpec(src=src, dst=dst, label=_cell(reason))
        for src, dst, reason in _edge_pairs(graph)
    ]
    return build_recipe_svg(title=title, nodes=specs, edges=edges)


def build_explanations(
    template: GraphTemplate,
    graph: ExecutionGraph,
    components: Sequence[NodeComponent],
    *,
    params: GraphTemplateParams,
) -> str:
    """Markdown section printed below the SVG drawing."""
    fields_by, shapes_by = _partition_components(components)
    parts: list[str] = [
        f"## Recipe `{template.name}`",
        "",
        template.summary or "",
        "",
        "### Recipe documentation",
        "",
        template.documentation(),
        "",
        "## Graph nodes",
        "",
    ]
    for nid, node in graph.nodes.items():
        parts.append(f"### `{nid}`")
        parts.append("")
        nest = _node_is_nest(node, shapes_by.get(nid) or [])
        shape = "round rect (nest/subgraph)" if nest else "square (concrete)"
        parts.append(f"{_node_blurb(node)} · render shape: **{shape}**")
        parts.append("")
        field_comps = fields_by.get(nid) or []
        if field_comps:
            parts.append("| name | type | value |")
            parts.append("| --- | --- | --- |")
            for comp in field_comps:
                name = comp.soft_point_name or comp.label
                typ = comp.soft_point_kind or "other"
                value = _field_value(
                    name, template=template, params=params, detail=comp.detail
                )
                parts.append(f"| `{name}` | `{typ}` | `{value}` |")
            parts.append("")
            for comp in field_comps:
                name = comp.soft_point_name or comp.label
                parts.append(f"- **`{name}`** — {_component_blurb(comp, template)}")
            parts.append("")

        flow = _ordered_flow_comps(shapes_by.get(nid) or [])
        if flow:
            seq = " → ".join(f"`{_comp_plain_label(c)}`" for c in flow)
            parts.append(
                f"Interior sequence **inside** container `{nid}` "
                f"(start → … → end): {seq}"
            )
            parts.append("")

    parts.append("## Interior steps (inside loop / nest containers)")
    parts.append("")
    shape_comps = [
        c for nid in graph.nodes for c in _ordered_flow_comps(shapes_by.get(nid) or [])
    ]
    if not shape_comps:
        parts.append("_No interior loop/nest steps for this instantiation._")
        parts.append("")
    else:
        for comp in shape_comps:
            parts.append(f"### `{comp.id}`")
            parts.append("")
            nest = _is_nest_component(comp)
            shape = "round rect" if nest else "square"
            parts.append(
                f"Inside `{comp.parent_node_id}` · kind=`{comp.kind}` · "
                f"shape: **{shape}**"
            )
            parts.append("")
            parts.append(_component_blurb(comp, template))
            parts.append("")

    parts.append("## Kind legend")
    parts.append("")
    kinds_used = sorted({str(c.kind) for c in components})
    for kind in kinds_used or sorted(_COMPONENT_KIND_DOCS.keys()):
        parts.append(f"- **`{kind}`** — {_COMPONENT_KIND_DOCS.get(kind, '')}")
    parts.append("")
    parts.append(
        "Outer edges are recipe **execution flow**. Loop/nest nodes are "
        "**round containers** that contain their interiors; interiors are sequenced "
        "with `then` (not unrolled onto the outer path, not a parent fan-out). "
        "Configuration soft points are ER-style **name | type | value** tables. "
        "Concrete steps stay **square**. Diagrams are SVG from MechaHarness's "
        "layout engine (`recipe_diagram`), not Mermaid."
    )
    parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_recipe(
    name: str,
    *,
    soft_bindings: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    goal: str | None = None,
    params: GraphTemplateParams | None = None,
    registry: Any = None,
    tool_names: Sequence[str] | None = None,
) -> RecipeRender:
    """Instantiate ``name`` and produce SVG + explanation markdown."""
    template = get_recipe(name, registry=resolve_registry(registry))
    use_params = params or _default_params(
        template,
        soft_bindings=soft_bindings,
        inputs=inputs,
        goal=goal,
    )
    graph = template.instantiate(use_params)
    harness_parent = next(
        (
            nid
            for nid, node in graph.nodes.items()
            if node.kind == "harness_loop" or nid == "harness_loop"
        ),
        None,
    )
    tools_parent = next(
        (
            nid
            for nid, node in graph.nodes.items()
            if node.kind in {"conversational_tool_loop", "tools"}
            or nid.endswith("/tools")
            or nid == "tools"
        ),
        None,
    )
    components = list(
        node_components_for(
            graph,
            template=template,
            tool_names=tool_names if tools_parent is not None else None,
            tools_parent_id=tools_parent,
        )
    )
    if harness_parent is not None:
        components.extend(
            node_components_for_harness(
                parent_node_id=harness_parent,
                tool_names=tool_names,
            )
        )
    seen: set[str] = set()
    unique: list[NodeComponent] = []
    for comp in components:
        if comp.id in seen:
            continue
        seen.add(comp.id)
        unique.append(comp)
    components = unique

    fields_by, _shapes_by = _partition_components(components)
    fields_payload = {
        nid: [
            {
                "name": c.soft_point_name or c.label,
                "kind": c.soft_point_kind,
                "value": _field_value(
                    c.soft_point_name or c.label,
                    template=template,
                    params=use_params,
                    detail=c.detail,
                ),
            }
            for c in comps
        ]
        for nid, comps in fields_by.items()
    }

    svg = build_svg(
        graph,
        components,
        title=template.name,
        template=template,
        params=use_params,
    )
    explanations = build_explanations(
        template, graph, components, params=use_params
    )
    return RecipeRender(
        recipe=template.name,
        version=template.version,
        summary=template.summary,
        svg=svg,
        explanations_markdown=explanations,
        nodes=[
            {
                "id": n.id,
                "kind": n.kind,
                "goal": n.goal,
                "depends_on": list(n.depends_on),
            }
            for n in graph.nodes.values()
        ],
        components=[c.model_dump(mode="json") for c in components],
        fields_by_node=fields_payload,
    )


def format_render_document(result: RecipeRender, *, svg_path: str | None = None) -> str:
    """Markdown document: diagram reference first, explanations below."""
    header = (
        f"# Render `{result.recipe}` v{result.version}\n\n"
        f"{result.summary}\n\n"
        "## Graph\n\n"
    )
    if svg_path:
        graph_block = f"![`{result.recipe}`]({svg_path})\n\nSVG written to `{svg_path}`.\n"
    else:
        graph_block = (
            "SVG diagram (open the `.svg` file written by "
            "`mechaharness recipes render --out …`).\n"
        )
    return f"{header}{graph_block}\n---\n\n{result.explanations_markdown}"


__all__ = [
    "RecipeRender",
    "build_explanations",
    "build_svg",
    "format_render_document",
    "render_recipe",
]
