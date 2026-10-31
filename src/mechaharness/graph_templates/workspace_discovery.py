"""Read-only workspace discovery Agentic Recipe (gastronomic M5).

Composes P0 discovery hard nodes with two bag-aware inference soft points.
Does not mutate the target workspace.
"""

from __future__ import annotations

from typing import Any

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)
from mechaharness.isolation.isolation_contract import TemplateIOContract


class WorkspaceDiscoveryTemplate(GraphTemplate):
    """Preflight → manifest → hypotheses → search/extract → interpret → verify → publish.

    Soft points bind inference payloads (ContextSpec / completion scripts) and
    hard-node parameter overrides. Catalog id: ``workspace_discovery``.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, WorkspaceDiscoveryTemplate,
        ... )
        >>> graph = WorkspaceDiscoveryTemplate().instantiate(GraphTemplateParams(
        ...     goal="Find division-by-zero handling",
        ...     inputs={
        ...         "goal": "Find division-by-zero handling",
        ...         "workspace": {"root": "."},
        ...         "constraints": {"read_only": True, "max_files": 100},
        ...     },
        ... ))
        >>> graph.template_name
        'workspace_discovery'
    """

    name = "workspace_discovery"
    version = "1"
    summary = (
        "Read-only workspace discovery: hard enumeration/search/verify with two "
        "bounded inference steps publishing a typed WorkspaceInventory."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "workspace": "object",
            "constraints": "object",
        },
        outputs={"workspace_inventory": "object"},
    )
    soft_points = (
        SoftPoint(
            name="hypotheses_payload",
            kind="task_state",
            description="Payload for the hypotheses inference node (context/completion)",
            required=False,
        ),
        SoftPoint(
            name="interpret_payload",
            kind="task_state",
            description="Payload for the interpret inference node (context/completion)",
            required=False,
        ),
        SoftPoint(
            name="manifest_max_files",
            kind="budget",
            description="Max files for workspace_manifest",
            required=False,
            default=100,
        ),
        SoftPoint(
            name="search_max_matches",
            kind="budget",
            description="Max matches for file_search",
            required=False,
            default=50,
        ),
        SoftPoint(
            name="min_files_scanned",
            kind="budget",
            description="Coverage floor for coverage_measure",
            required=False,
            default=1,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or "discover workspace")
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
        if "workspace" in inputs:
            seed_put["in.workspace"] = inputs["workspace"]
        if "constraints" in inputs:
            seed_put["in.constraints"] = inputs["constraints"]
        # Seed node so hosts can inject bag state without a separate verb.
        graph.add_node(
            make_node(
                id="seed",
                kind="compute",
                payload={"bag_put": seed_put} if seed_put else {},
            )
        )
        graph.add_node(
            make_node(
                id="preflight",
                kind="discovery_preflight",
                depends_on=["seed"],
                payload={
                    "reads": {
                        "goal": "in.goal",
                        "workspace": "in.workspace",
                        "constraints": "in.constraints",
                    },
                    "writes": {"destination": "acc.discovery.preflight"},
                    "parameters": {"fail_if_invalid": True},
                },
            )
        )
        max_files = int(
            bindings.get(
                "manifest_max_files",
                (inputs.get("constraints") or {}).get("max_files", 100)
                if isinstance(inputs.get("constraints"), dict)
                else 100,
            )
        )
        graph.add_node(
            make_node(
                id="manifest",
                kind="workspace_manifest",
                depends_on=["preflight"],
                payload={
                    "reads": {"workspace": "in.workspace"},
                    "writes": {"destination": "acc.discovery.manifest"},
                    "parameters": {"max_files": max_files},
                },
            )
        )
        hyp_payload = dict(bindings.get("hypotheses_payload") or {})
        hyp_payload.setdefault("soft_point", "hypotheses_payload")
        hyp_payload.setdefault(
            "context",
            {
                "version": "1",
                "system": "Propose search hypotheses as JSON only.",
                "reads": [
                    {"path": "in.goal", "required": True},
                    {"path": "acc.discovery.manifest.coverage", "required": True},
                ],
                "response": {"writes": "acc.discovery.hypotheses", "parse": "json"},
            },
        )
        graph.add_node(
            make_node(
                id="hypotheses",
                kind="infer",
                depends_on=["manifest"],
                payload=hyp_payload,
            )
        )
        max_matches = int(
            bindings.get(
                "search_max_matches",
                (inputs.get("constraints") or {}).get("max_search_results", 50)
                if isinstance(inputs.get("constraints"), dict)
                else 50,
            )
        )
        graph.add_node(
            make_node(
                id="search",
                kind="file_search",
                depends_on=["hypotheses"],
                payload={
                    "reads": {
                        "workspace": "in.workspace",
                        "manifest": "acc.discovery.manifest",
                        "queries": "acc.discovery.hypotheses",
                    },
                    "writes": {"destination": "acc.discovery.matches"},
                    "parameters": {"max_matches": max_matches},
                },
            )
        )
        graph.add_node(
            make_node(
                id="extract",
                kind="source_extract",
                depends_on=["search"],
                payload={
                    "reads": {
                        "workspace": "in.workspace",
                        "manifest": "acc.discovery.manifest",
                        "requests": "acc.discovery.hypotheses",
                        "matches": "acc.discovery.matches",
                    },
                    "writes": {"destination": "acc.discovery.excerpts"},
                    "on_error": {
                        "destination": "acc.discovery.excerpts",
                        "policy": "report",
                    },
                },
            )
        )
        interpret_payload = dict(bindings.get("interpret_payload") or {})
        interpret_payload.setdefault("soft_point", "interpret_payload")
        interpret_payload.setdefault(
            "context",
            {
                "version": "1",
                "system": "Propose verified findings as JSON only.",
                "reads": [
                    {"path": "in.goal", "required": True},
                    {"path": "acc.discovery.hypotheses", "required": True},
                    {"path": "acc.discovery.matches", "required": True},
                    {"path": "acc.discovery.excerpts", "required": False},
                ],
                "response": {
                    "writes": "acc.discovery.proposed_findings",
                    "parse": "json",
                },
            },
        )
        graph.add_node(
            make_node(
                id="interpret",
                kind="infer",
                depends_on=["extract"],
                payload=interpret_payload,
            )
        )
        graph.add_node(
            make_node(
                id="resolve",
                kind="evidence_resolve",
                depends_on=["interpret"],
                payload={
                    "reads": {
                        "proposals": "acc.discovery.proposed_findings",
                        "manifest": "acc.discovery.manifest",
                        "excerpts": "acc.discovery.excerpts",
                    },
                    "writes": {"destination": "acc.discovery.verified"},
                },
            )
        )
        min_files = int(bindings.get("min_files_scanned", 1))
        graph.add_node(
            make_node(
                id="coverage",
                kind="coverage_measure",
                depends_on=["resolve"],
                payload={
                    "reads": {
                        "manifest": "acc.discovery.manifest",
                        "search": "acc.discovery.matches",
                    },
                    "writes": {"destination": "acc.discovery.coverage"},
                    "parameters": {"min_files_scanned": min_files},
                },
            )
        )
        graph.add_node(
            make_node(
                id="publish",
                kind="inventory_publish",
                depends_on=["coverage"],
                payload={
                    "reads": {
                        "goal": "in.goal",
                        "manifest": "acc.discovery.manifest",
                        "verified": "acc.discovery.verified",
                        "coverage": "acc.discovery.coverage",
                        "proposed": "acc.discovery.proposed_findings",
                        "preflight": "acc.discovery.preflight",
                    },
                    "writes": {"destination": "out.workspace_inventory"},
                },
            )
        )
        order = [
            "seed",
            "preflight",
            "manifest",
            "hypotheses",
            "search",
            "extract",
            "interpret",
            "resolve",
            "coverage",
            "publish",
        ]
        for left, right in zip(order, order[1:]):
            graph.add_dependency(
                DependencyEdge(
                    from_node=left,
                    to_node=right,
                    types=["control"],
                    reason="workspace_discovery",
                )
            )
        return graph


__all__ = ["WorkspaceDiscoveryTemplate"]
