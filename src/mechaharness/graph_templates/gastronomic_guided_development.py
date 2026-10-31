"""Product recipe: discovery → contract → plan (gastronomic M6 skeleton).

Catalog id: ``gastronomic_guided_development``. Mutating coding stages are
deferred; this increment tiles read-only discovery, contract extraction, and
change decomposition. ``guided_coding`` remains the unchanged baseline.
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
from mechaharness.graph_templates.change_decomposition import ChangeDecompositionTemplate
from mechaharness.graph_templates.contract_extraction import ContractExtractionTemplate
from mechaharness.graph_templates.workspace_discovery import WorkspaceDiscoveryTemplate
from mechaharness.isolation.isolation_contract import TemplateIOContract


class GastronomicGuidedDevelopmentTemplate(GraphTemplate):
    """Seed → discovery → contract → plan tiles.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, GastronomicGuidedDevelopmentTemplate,
        ... )
        >>> graph = GastronomicGuidedDevelopmentTemplate().instantiate(
        ...     GraphTemplateParams(goal="Add multiplication safely")
        ... )
        >>> graph.template_name
        'gastronomic_guided_development'
        >>> "plan_tile" in graph.nodes
        True
    """

    name = "gastronomic_guided_development"
    version = "1"
    category = "agentic_recipe"
    summary = (
        "Read-only workspace discovery, ChangeContract freeze, then ChangePlan "
        "decomposition before coding; later M6 stages add execute/verify."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "workspace": "object",
            "constraints": "object",
        },
        outputs={
            "workspace_inventory": "object",
            "change_contract": "object",
            "change_plan": "object",
        },
    )
    soft_points = (
        SoftPoint(
            name="discovery_bindings",
            kind="task_state",
            description="Soft bindings forwarded to workspace_discovery",
            required=False,
            default={},
        ),
        SoftPoint(
            name="contract_bindings",
            kind="task_state",
            description="Soft bindings forwarded to contract_extraction",
            required=False,
            default={},
        ),
        SoftPoint(
            name="plan_bindings",
            kind="task_state",
            description="Soft bindings forwarded to change_decomposition",
            required=False,
            default={},
        ),
        SoftPoint(
            name="hypotheses_payload",
            kind="task_state",
            description="Optional discovery hypotheses_payload soft point",
            required=False,
        ),
        SoftPoint(
            name="interpret_payload",
            kind="task_state",
            description="Optional discovery interpret_payload soft point",
            required=False,
        ),
        SoftPoint(
            name="propose_payload",
            kind="task_state",
            description="Optional contract propose_payload soft point",
            required=False,
        ),
        SoftPoint(
            name="plan_propose_payload",
            kind="task_state",
            description="Optional plan propose_payload soft point",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or self.name)
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
        if "workspace" in inputs:
            seed_put["in.workspace"] = inputs["workspace"]
        if "constraints" in inputs:
            seed_put["in.constraints"] = inputs["constraints"]
        graph.add_node(
            make_node(
                id="seed",
                kind="compute",
                payload={"bag_put": seed_put} if seed_put else {},
            )
        )

        discovery_soft = dict(bindings.get("discovery_bindings") or {})
        for key in ("hypotheses_payload", "interpret_payload"):
            if key in bindings and key not in discovery_soft:
                discovery_soft[key] = bindings[key]
        _discovery_child, discovery_embed = WorkspaceDiscoveryTemplate().tile(
            GraphTemplateParams(
                goal=f"{goal}:discover",
                instance_key="discovery",
                inputs={
                    "goal": seed_put.get("in.goal", goal),
                    "workspace": inputs.get("workspace") or {"root": "."},
                    "constraints": inputs.get("constraints")
                    or {"read_only": True, "max_files": 100},
                },
                soft_bindings=discovery_soft,
            ),
            parent_node_id="discovery_tile",
        )
        del _discovery_child
        discovery_embed.depends_on = ["seed"]
        discovery_embed.payload = {
            **dict(discovery_embed.payload or {}),
            "bag_inputs": {
                "in.goal": "in.goal",
                "in.workspace": "in.workspace",
                "in.constraints": "in.constraints",
            },
            "bag_outputs": {
                "acc.stages.discovery": "out.workspace_inventory",
            },
        }
        graph.add_node(discovery_embed)

        contract_soft = dict(bindings.get("contract_bindings") or {})
        if "propose_payload" in bindings and "propose_payload" not in contract_soft:
            contract_soft["propose_payload"] = bindings["propose_payload"]
        _contract_child, contract_embed = ContractExtractionTemplate().tile(
            GraphTemplateParams(
                goal=f"{goal}:contract",
                instance_key="contract",
                inputs={"goal": seed_put.get("in.goal", goal)},
                soft_bindings=contract_soft,
            ),
            parent_node_id="contract_tile",
        )
        del _contract_child
        contract_embed.depends_on = ["discovery_tile"]
        contract_embed.payload = {
            **dict(contract_embed.payload or {}),
            "bag_inputs": {
                "in.goal": "in.goal",
                "in.workspace_inventory": "acc.stages.discovery",
            },
            "bag_outputs": {
                "acc.stages.contract": "out.change_contract",
            },
        }
        graph.add_node(contract_embed)

        plan_soft = dict(bindings.get("plan_bindings") or {})
        if (
            "plan_propose_payload" in bindings
            and "propose_payload" not in plan_soft
        ):
            plan_soft["propose_payload"] = bindings["plan_propose_payload"]
        _plan_child, plan_embed = ChangeDecompositionTemplate().tile(
            GraphTemplateParams(
                goal=f"{goal}:plan",
                instance_key="plan",
                inputs={"goal": seed_put.get("in.goal", goal)},
                soft_bindings=plan_soft,
            ),
            parent_node_id="plan_tile",
        )
        del _plan_child
        plan_embed.depends_on = ["contract_tile"]
        plan_embed.payload = {
            **dict(plan_embed.payload or {}),
            "bag_inputs": {
                "in.goal": "in.goal",
                "in.change_contract": "acc.stages.contract",
                "in.workspace_inventory": "acc.stages.discovery",
            },
            "bag_outputs": {
                "acc.stages.plan": "out.change_plan",
            },
        }
        graph.add_node(plan_embed)

        graph.add_node(
            make_node(
                id="publish",
                kind="bag_project",
                depends_on=["plan_tile"],
                payload={
                    "reads": {"source": "acc.stages.plan"},
                    "writes": {"destination": "out.change_plan"},
                    "parameters": {
                        "fields": [
                            "version",
                            "status",
                            "objective",
                            "slices",
                            "constraints",
                            "provenance",
                        ]
                    },
                },
            )
        )
        graph.add_node(
            make_node(
                id="publish_contract",
                kind="bag_project",
                depends_on=["publish"],
                payload={
                    "reads": {"source": "acc.stages.contract"},
                    "writes": {"destination": "out.change_contract"},
                    "parameters": {
                        "fields": [
                            "version",
                            "status",
                            "objective",
                            "requested_behavior",
                            "invariants",
                            "prohibited_changes",
                            "verification",
                            "assumptions",
                            "unknowns",
                            "provenance",
                        ]
                    },
                },
            )
        )
        graph.add_node(
            make_node(
                id="publish_inventory",
                kind="bag_project",
                depends_on=["publish_contract"],
                payload={
                    "reads": {"source": "acc.stages.discovery"},
                    "writes": {"destination": "out.workspace_inventory"},
                    "parameters": {
                        "fields": [
                            "status",
                            "objective",
                            "workspace_revision",
                            "relevant_files",
                            "tests",
                            "unknowns",
                            "coverage",
                            "rejected_claims",
                        ]
                    },
                },
            )
        )

        for left, right in (
            ("seed", "discovery_tile"),
            ("discovery_tile", "contract_tile"),
            ("contract_tile", "plan_tile"),
            ("plan_tile", "publish"),
            ("publish", "publish_contract"),
            ("publish_contract", "publish_inventory"),
        ):
            graph.add_dependency(
                DependencyEdge(
                    from_node=left,
                    to_node=right,
                    types=["control"],
                    reason="gastronomic_guided_development",
                )
            )
        return graph


__all__ = ["GastronomicGuidedDevelopmentTemplate"]
