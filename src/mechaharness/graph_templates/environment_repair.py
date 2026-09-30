"""Environment repair subgraph template.

Diagnose missing substrate capabilities, run a bounded repair loop, then
recheck so linkage can succeed before dependent graph work continues.
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


class EnvironmentRepairTemplate(GraphTemplate):
    """Diagnose → bounded env repair → recheck."""

    name = "environment_repair"
    version = "1"
    summary = (
        "Bounded subgraph to repair missing environment capabilities "
        "(secrets, routes, binaries, capacity) before dependent work resumes."
    )
    soft_points = (
        SoftPoint(
            name="diagnose_kind",
            kind="runner_kind",
            description="Diagnosis node kind",
            default="env_diagnose",
        ),
        SoftPoint(
            name="repair_kind",
            kind="runner_kind",
            description="Repair loop node kind",
            default="env_repair",
        ),
        SoftPoint(
            name="recheck_kind",
            kind="runner_kind",
            description="Post-repair environment recheck kind",
            default="env_recheck",
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
            description="Acceptance on recheck (default environment_ok)",
            default=["environment_ok"],
        ),
        SoftPoint(
            name="diagnosis_inputs",
            kind="task_state",
            description="Payload for diagnose (via params.inputs)",
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        stop = params.stop_contract or StopContract(version="1", max_iterations=2)
        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        diagnose = make_node(
            id="diagnose",
            kind=str(bindings.get("diagnose_kind", "env_diagnose")),
            goal="diagnose environment",
            payload=dict(params.inputs),
        )
        repair = make_node(
            id="repair_env",
            kind=str(bindings.get("repair_kind", "env_repair")),
            goal="repair environment",
            depends_on=[diagnose.id],
            repeating=True,
            stop_contract=stop,
            payload={"phase": "repair"},
        )
        recheck = make_node(
            id="recheck",
            kind=str(bindings.get("recheck_kind", "env_recheck")),
            goal="re-resolve environment",
            depends_on=[repair.id],
            acceptance=params.acceptance or ["environment_ok"],
        )
        for node in (diagnose, repair, recheck):
            graph.add_node(node)
        graph.add_dependency(
            DependencyEdge(
                from_node=diagnose.id, to_node=repair.id, types=["data"], reason="diagnosis"
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=repair.id, to_node=recheck.id, types=["control"], reason="recheck"
            )
        )
        return graph
