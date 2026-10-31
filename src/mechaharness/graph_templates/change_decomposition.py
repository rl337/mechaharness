"""ChangePlan decomposition Agentic Recipe (gastronomic M6 increment 2).

Consumes a ChangeContract (and optional inventory), freezes plan constraints,
optionally infers ordered slices, and publishes a typed ChangePlan. Does not
mutate the workspace.
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


class ChangeDecompositionTemplate(GraphTemplate):
    """Constrain → propose slices → assemble → validate.

    Catalog id: ``change_decomposition``.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, ChangeDecompositionTemplate,
        ... )
        >>> graph = ChangeDecompositionTemplate().instantiate(GraphTemplateParams(
        ...     goal="Plan multiplication",
        ...     inputs={
        ...         "goal": "Plan multiplication",
        ...         "change_contract": {
        ...             "version": "1",
        ...             "status": "ok",
        ...             "objective": "Add multiplication",
        ...             "invariants": [],
        ...             "verification": [{"pytest": True}],
        ...         },
        ...     },
        ... ))
        >>> graph.template_name
        'change_decomposition'
    """

    name = "change_decomposition"
    version = "1"
    summary = (
        "Decompose a ChangeContract into ordered ChangePlan slices with "
        "scope, checks, rollback, and dependency order before coding."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "change_contract": "object",
            "workspace_inventory": "object",
        },
        outputs={"change_plan": "object"},
    )
    soft_points = (
        SoftPoint(
            name="propose_payload",
            kind="task_state",
            description="Payload for the plan proposal inference node",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or "decompose change plan")
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
        if "change_contract" in inputs:
            seed_put["in.change_contract"] = inputs["change_contract"]
        if "workspace_inventory" in inputs:
            seed_put["in.workspace_inventory"] = inputs["workspace_inventory"]
        graph.add_node(
            make_node(
                id="seed",
                kind="compute",
                payload={"bag_put": seed_put} if seed_put else {},
            )
        )
        graph.add_node(
            make_node(
                id="constrain",
                kind="plan_constrain",
                depends_on=["seed"],
                payload={
                    "reads": {"contract": "in.change_contract"},
                    "writes": {"destination": "acc.plan.constraints"},
                },
            )
        )
        propose_payload = dict(bindings.get("propose_payload") or {})
        propose_payload.setdefault("soft_point", "propose_payload")
        propose_payload.setdefault(
            "context",
            {
                "version": "1",
                "system": (
                    "Propose a ChangePlan as JSON only. "
                    "Each slice needs id, title, scope, checks, rollback, "
                    "and depends_on. Prefer small ordered slices."
                ),
                "reads": [
                    {"path": "in.goal", "required": True},
                    {"path": "in.change_contract", "required": True},
                    {"path": "acc.plan.constraints", "required": True},
                    {"path": "in.workspace_inventory", "required": False},
                ],
                "response": {
                    "writes": "acc.plan.proposed",
                    "parse": "json",
                },
            },
        )
        graph.add_node(
            make_node(
                id="propose",
                kind="infer",
                depends_on=["constrain"],
                payload=propose_payload,
            )
        )
        graph.add_node(
            make_node(
                id="assemble",
                kind="plan_assemble",
                depends_on=["propose"],
                payload={
                    "reads": {
                        "contract": "in.change_contract",
                        "proposed": "acc.plan.proposed",
                        "constraints": "acc.plan.constraints",
                        "inventory": "in.workspace_inventory",
                    },
                    "writes": {"destination": "out.change_plan"},
                },
            )
        )
        graph.add_node(
            make_node(
                id="validate",
                kind="plan_validate",
                depends_on=["assemble"],
                payload={
                    "reads": {"source": "out.change_plan"},
                    "writes": {"destination": "acc.plan.validation"},
                    "parameters": {"fail_if_invalid": True},
                },
            )
        )
        order = ["seed", "constrain", "propose", "assemble", "validate"]
        for left, right in zip(order, order[1:]):
            graph.add_dependency(
                DependencyEdge(
                    from_node=left,
                    to_node=right,
                    types=["control"],
                    reason="change_decomposition",
                )
            )
        return graph


__all__ = ["ChangeDecompositionTemplate"]
