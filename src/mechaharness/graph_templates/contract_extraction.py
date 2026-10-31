"""ChangeContract extraction Agentic Recipe (gastronomic M6 increment 1).

Consumes a verified WorkspaceInventory plus objective, freezes prior
invariants, optionally infers semantic requirements, and publishes a typed
ChangeContract. Does not mutate the workspace.
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


class ContractExtractionTemplate(GraphTemplate):
    """Freeze inventory invariants → propose semantics → assemble → validate.

    Catalog id: ``contract_extraction``.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, ContractExtractionTemplate,
        ... )
        >>> graph = ContractExtractionTemplate().instantiate(GraphTemplateParams(
        ...     goal="Add multiplication",
        ...     inputs={
        ...         "goal": "Add multiplication",
        ...         "workspace_inventory": {"status": "found", "relevant_files": []},
        ...     },
        ... ))
        >>> graph.template_name
        'contract_extraction'
    """

    name = "contract_extraction"
    version = "1"
    summary = (
        "Freeze verified discovery invariants and publish a typed ChangeContract "
        "before any mutating coding step."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "workspace_inventory": "object",
        },
        outputs={"change_contract": "object"},
    )
    soft_points = (
        SoftPoint(
            name="propose_payload",
            kind="task_state",
            description="Payload for the contract proposal inference node",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or "extract change contract")
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
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
                id="freeze",
                kind="invariant_freeze",
                depends_on=["seed"],
                payload={
                    "reads": {
                        "inventory": "in.workspace_inventory",
                        "goal": "in.goal",
                    },
                    "writes": {"destination": "acc.contract.frozen"},
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
                    "Propose ChangeContract semantics as JSON only. "
                    "Do not drop prior verified files."
                ),
                "reads": [
                    {"path": "in.goal", "required": True},
                    {"path": "in.workspace_inventory", "required": True},
                    {"path": "acc.contract.frozen", "required": True},
                ],
                "response": {
                    "writes": "acc.contract.proposed",
                    "parse": "json",
                },
            },
        )
        graph.add_node(
            make_node(
                id="propose",
                kind="infer",
                depends_on=["freeze"],
                payload=propose_payload,
            )
        )
        graph.add_node(
            make_node(
                id="assemble",
                kind="contract_assemble",
                depends_on=["propose"],
                payload={
                    "reads": {
                        "goal": "in.goal",
                        "inventory": "in.workspace_inventory",
                        "proposed": "acc.contract.proposed",
                        "frozen": "acc.contract.frozen",
                    },
                    "writes": {"destination": "out.change_contract"},
                },
            )
        )
        graph.add_node(
            make_node(
                id="validate",
                kind="contract_validate",
                depends_on=["assemble"],
                payload={
                    "reads": {"source": "out.change_contract"},
                    "writes": {"destination": "acc.contract.validation"},
                    "parameters": {"fail_if_invalid": True},
                },
            )
        )
        order = ["seed", "freeze", "propose", "assemble", "validate"]
        for left, right in zip(order, order[1:]):
            graph.add_dependency(
                DependencyEdge(
                    from_node=left,
                    to_node=right,
                    types=["control"],
                    reason="contract_extraction",
                )
            )
        return graph


__all__ = ["ContractExtractionTemplate"]
