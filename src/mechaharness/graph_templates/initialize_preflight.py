"""Initialize / preflight graph template.

WalkingLabs L06 treats initialization as its own phase before substantive work
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-06-why-initialization-needs-its-own-phase/).

Linkage, environment/capability checks, baseline verification, and checkpoint
compatibility run before ready output::

    >>> from mechaharness.graph_templates import (
    ...     GraphTemplateParams, InitializePreflightTemplate,
    ... )
    >>> graph = InitializePreflightTemplate().instantiate(GraphTemplateParams(
    ...     goal="preflight before deploy",
    ... ))
    >>> sorted(graph.nodes)
    ['capability_check', 'checkpoint_compat', 'linkage', 'ready']
"""

from __future__ import annotations

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)


class InitializePreflightTemplate(GraphTemplate):
    """Linkage → capability check → checkpoint compat → ready."""

    name = "initialize_preflight"
    version = "1"
    summary = (
        "Reusable initialize/preflight skeleton: linkage, environment/capability "
        "checks, checkpoint compatibility, then readiness before substantive nodes."
    )
    soft_points = (
        SoftPoint(
            name="linkage_kind",
            kind="runner_kind",
            description="Linkage resolution node kind",
            default="preflight_linkage",
        ),
        SoftPoint(
            name="capability_kind",
            kind="runner_kind",
            description="Environment/capability check kind",
            default="preflight_capability",
        ),
        SoftPoint(
            name="checkpoint_kind",
            kind="runner_kind",
            description="Checkpoint compatibility check kind",
            default="preflight_checkpoint",
        ),
        SoftPoint(
            name="ready_kind",
            kind="runner_kind",
            description="Readiness output node kind",
            default="preflight_ready",
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        b = params.soft_bindings
        graph = ExecutionGraph(goal=params.goal or "initialize preflight")
        linkage = make_node(
            id="linkage",
            kind=str(b.get("linkage_kind") or "preflight_linkage"),
            goal="resolve linkage",
        )
        capability = make_node(
            id="capability_check",
            kind=str(b.get("capability_kind") or "preflight_capability"),
            goal="check environment capabilities",
        )
        checkpoint = make_node(
            id="checkpoint_compat",
            kind=str(b.get("checkpoint_kind") or "preflight_checkpoint"),
            goal="validate checkpoint compatibility",
        )
        ready = make_node(
            id="ready",
            kind=str(b.get("ready_kind") or "preflight_ready"),
            goal="emit readiness",
            acceptance=["preflight_ok"],
        )
        for node in (linkage, capability, checkpoint, ready):
            graph.add_node(node)
        graph.add_dependency(
            DependencyEdge(
                from_node="linkage",
                to_node="capability_check",
                types=["data"],
                reason="capability checks need resolved linkage",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node="capability_check",
                to_node="checkpoint_compat",
                types=["data"],
                reason="checkpoint checks need capability baseline",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node="checkpoint_compat",
                to_node="ready",
                types=["data"],
                reason="ready only after checkpoint compatibility",
            )
        )
        return graph
