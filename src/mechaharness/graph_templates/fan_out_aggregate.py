"""Fan-out then aggregate subgraph template.

Plan work, run independent branches in parallel (subject to write-scope
serialization), then reduce with a hierarchical fan-in budget. Clients bind
branch runner kinds, payloads, and reduction policy via soft points.
"""

from __future__ import annotations

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)


class FanOutAggregateTemplate(GraphTemplate):
    """Produce N branches then aggregate results."""

    name = "fan_out_aggregate"
    version = "1"
    summary = (
        "Plan → fan-out independent branches → reduce/aggregate. "
        "Use for parallel research, multi-path exploration, or map-reduce style work."
    )
    soft_points = (
        SoftPoint(
            name="plan_kind",
            kind="runner_kind",
            description="Node kind for the planning step",
            default="plan",
        ),
        SoftPoint(
            name="branch_kind",
            kind="runner_kind",
            description="Node kind for each fan-out branch",
            default="branch",
        ),
        SoftPoint(
            name="reduce_kind",
            kind="runner_kind",
            description="Node kind for aggregation / fan-in",
            default="reduce",
        ),
        SoftPoint(
            name="branch_payloads",
            kind="task_state",
            description="Per-branch payload dicts (write_scopes optional)",
            required=False,
        ),
        SoftPoint(
            name="fan_in_budget",
            kind="budget",
            description="Max items retained by hierarchical fan-in at reduce time",
            default=8,
        ),
        SoftPoint(
            name="acceptance",
            kind="policy",
            description="Acceptance criteria attached to the reduce node",
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        plan_kind = str(bindings.get("plan_kind", "plan"))
        branch_kind = str(bindings.get("branch_kind", "branch"))
        reduce_kind = str(bindings.get("reduce_kind", "reduce"))
        fan_in_budget = int(
            bindings.get("fan_in_budget", params.inputs.get("fan_in_budget", 8))
        )

        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        plan = make_node(id="plan", kind=plan_kind, goal="plan fan-out", payload={"phase": "plan"})
        graph.add_node(plan)
        branch_ids: list[str] = []
        payloads = params.branch_payloads or [{"index": 0}]
        for i, branch in enumerate(payloads):
            nid = f"branch_{i}"
            node = make_node(
                id=nid,
                kind=branch_kind,
                goal=f"branch {i}",
                depends_on=[plan.id],
                payload=dict(branch),
                write_scopes=list(branch.get("write_scopes") or []),
            )
            graph.add_node(node)
            graph.add_dependency(
                DependencyEdge(
                    from_node=plan.id,
                    to_node=nid,
                    types=["control"],
                    reason="fan_out",
                )
            )
            branch_ids.append(nid)
        reduce = make_node(
            id="reduce",
            kind=reduce_kind,
            goal="aggregate branches",
            depends_on=branch_ids,
            payload={"fan_in_budget": fan_in_budget},
            acceptance=params.acceptance,
        )
        graph.add_node(reduce)
        for bid in branch_ids:
            graph.add_dependency(
                DependencyEdge(
                    from_node=bid,
                    to_node=reduce.id,
                    types=["data"],
                    reason="fan_in",
                )
            )
        return graph
