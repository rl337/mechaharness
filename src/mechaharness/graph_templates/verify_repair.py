"""Verify-then-repair subgraph template.

Produce an artifact, verify it, then run a bounded repair loop under an
explicit :class:`~mechaharness.stop_contract.StopContract`. Prefer deterministic
oracles when clients bind verification runners.
"""

from __future__ import annotations

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)
from mechaharness.stop_contract import StopContract


class VerifyRepairTemplate(GraphTemplate):
    """Produce → verify → bounded repair → complete."""

    name = "verify_repair"
    version = "1"
    summary = (
        "Produce an artifact, verify against acceptance, then repair under a "
        "stop contract until verification succeeds or budgets exhaust."
    )
    soft_points = (
        SoftPoint(
            name="produce_kind",
            kind="runner_kind",
            description="Node kind that produces the artifact",
            default="produce",
        ),
        SoftPoint(
            name="verify_kind",
            kind="runner_kind",
            description="Node kind that verifies the artifact",
            default="verify",
        ),
        SoftPoint(
            name="repair_kind",
            kind="runner_kind",
            description="Node kind for bounded repair iterations",
            default="repair",
        ),
        SoftPoint(
            name="complete_kind",
            kind="runner_kind",
            description="Terminal node kind after repair",
            default="complete",
        ),
        SoftPoint(
            name="stop_contract",
            kind="budget",
            description="StopContract for the repeating repair node",
            required=False,
        ),
        SoftPoint(
            name="acceptance",
            kind="policy",
            description="Acceptance criteria for verify/complete",
        ),
        SoftPoint(
            name="produce_inputs",
            kind="task_state",
            description="Payload for the produce node (via params.inputs)",
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        stop = params.stop_contract or StopContract(version="1", max_iterations=3)
        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        produce = make_node(
            id="produce",
            kind=str(bindings.get("produce_kind", "produce")),
            goal="produce artifact",
            payload=dict(params.inputs),
        )
        verify = make_node(
            id="verify",
            kind=str(bindings.get("verify_kind", "verify")),
            goal="verify artifact",
            depends_on=[produce.id],
            payload={"phase": "verify"},
            acceptance=params.acceptance,
        )
        repair = make_node(
            id="repair",
            kind=str(bindings.get("repair_kind", "repair")),
            goal="bounded repair",
            depends_on=[verify.id],
            repeating=True,
            stop_contract=stop,
            payload={"phase": "repair"},
        )
        done = make_node(
            id="complete",
            kind=str(bindings.get("complete_kind", "complete")),
            goal="mark complete",
            depends_on=[repair.id],
            acceptance=params.acceptance,
        )
        for node in (produce, verify, repair, done):
            graph.add_node(node)
        graph.add_dependency(
            DependencyEdge(
                from_node=produce.id, to_node=verify.id, types=["data"], reason="artifact"
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=verify.id, to_node=repair.id, types=["control"], reason="repair_gate"
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=repair.id, to_node=done.id, types=["control"], reason="done"
            )
        )
        return graph
