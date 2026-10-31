"""ChangeVerification Agentic Recipe (gastronomic M6 increment 4).

Runs host-observed verify_runs and immutable invariant hash checks against a
ChangeExecution + ChangeContract. Does not mutate the workspace.
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


class ChangeVerificationTemplate(GraphTemplate):
    """Constrain → host run → publish → validate.

    Catalog id: ``change_verification``.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, ChangeVerificationTemplate,
        ... )
        >>> graph = ChangeVerificationTemplate().instantiate(GraphTemplateParams(
        ...     goal="Verify multiply helper",
        ...     inputs={
        ...         "goal": "Verify multiply helper",
        ...         "change_execution": {"version": "1", "status": "ok"},
        ...         "change_contract": {"version": "1", "status": "ok"},
        ...         "workspace": {"root": "."},
        ...     },
        ... ))
        >>> graph.template_name
        'change_verification'
    """

    name = "change_verification"
    version = "1"
    summary = (
        "Host-observe ChangeExecution against ChangeContract checks and "
        "publish a typed VerificationReport."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "change_execution": "object",
            "change_contract": "object",
            "workspace": "object",
            "verify_runs": "object",
        },
        outputs={"verification_report": "object"},
    )
    soft_points = (
        SoftPoint(
            name="verify_payload",
            kind="task_state",
            description="Optional extra verify_runs / parameters for verification_run",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or "verify change execution")
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
        for key in (
            "change_execution",
            "change_contract",
            "workspace",
            "verify_runs",
        ):
            if key in inputs:
                seed_put[f"in.{key}"] = inputs[key]
        graph.add_node(
            make_node(
                id="seed",
                kind="compute",
                payload={"bag_put": seed_put} if seed_put else {},
            )
        )
        verify_payload = dict(bindings.get("verify_payload") or {})
        constrain_parameters = dict(verify_payload.get("parameters") or {})
        graph.add_node(
            make_node(
                id="constrain",
                kind="verification_constrain",
                depends_on=["seed"],
                payload={
                    "reads": {
                        "contract": "in.change_contract",
                        "execution": "in.change_execution",
                        "verify_runs": "in.verify_runs",
                    },
                    "writes": {"destination": "acc.verification.constraints"},
                    "parameters": constrain_parameters,
                },
            )
        )
        graph.add_node(
            make_node(
                id="run",
                kind="verification_run",
                depends_on=["constrain"],
                payload={
                    "soft_point": "verify_payload",
                    "reads": {
                        "constraints": "acc.verification.constraints",
                        "workspace": "in.workspace",
                    },
                    "writes": {"destination": "acc.verification.run_receipt"},
                },
            )
        )
        graph.add_node(
            make_node(
                id="publish",
                kind="verification_publish",
                depends_on=["run"],
                payload={
                    "reads": {
                        "constraints": "acc.verification.constraints",
                        "receipt": "acc.verification.run_receipt",
                    },
                    "writes": {"destination": "out.verification_report"},
                },
            )
        )
        graph.add_node(
            make_node(
                id="validate",
                kind="verification_validate",
                depends_on=["publish"],
                payload={
                    "reads": {"source": "out.verification_report"},
                    "writes": {"destination": "acc.verification.validation"},
                    "parameters": {"fail_if_invalid": True},
                },
            )
        )
        order = ["seed", "constrain", "run", "publish", "validate"]
        for left, right in zip(order, order[1:]):
            graph.add_dependency(
                DependencyEdge(
                    from_node=left,
                    to_node=right,
                    types=["control"],
                    reason="change_verification",
                )
            )
        return graph


__all__ = ["ChangeVerificationTemplate"]
