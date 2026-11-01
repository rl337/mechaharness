"""StrategyRevision Agentic Recipe (gastronomic M6 increment 6).

Deterministic retry / stop / yield gate over Diagnosis + plan + retry history.
Does not mutate the workspace; every retry disposition requires evidence delta
or an explicit strategy change / stop / yield.
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


class StrategyRevisionTemplate(GraphTemplate):
    """Constrain → decide → publish → validate.

    Catalog id: ``strategy_revision``.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, StrategyRevisionTemplate,
        ... )
        >>> graph = StrategyRevisionTemplate().instantiate(GraphTemplateParams(
        ...     goal="Revise after verify failure",
        ...     inputs={
        ...         "goal": "Revise after verify failure",
        ...         "diagnosis": {
        ...             "version": "1",
        ...             "status": "ok",
        ...             "failure_class": "semantics",
        ...             "next_experiment": "adjust_behavior_to_satisfy_failing_check",
        ...         },
        ...     },
        ... ))
        >>> graph.template_name
        'strategy_revision'
    """

    name = "strategy_revision"
    version = "1"
    summary = (
        "Deterministic retry/stop/yield gate from Diagnosis with evidence-delta "
        "or strategy-change requirements."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "diagnosis": "object",
            "change_plan": "object",
            "prior_attempts": "object",
            "retry_budget": "object",
        },
        outputs={"strategy_revision": "object"},
    )
    soft_points = (
        SoftPoint(
            name="revise_payload",
            kind="task_state",
            description="Optional parameters for revision_decide (e.g. attempts_max)",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or "revise after diagnosis")
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
        for key in ("diagnosis", "change_plan", "prior_attempts", "retry_budget"):
            if key in inputs:
                seed_put[f"in.{key}"] = inputs[key]
        graph.add_node(
            make_node(
                id="seed",
                kind="compute",
                payload={"bag_put": seed_put} if seed_put else {},
            )
        )
        revise_payload = dict(bindings.get("revise_payload") or {})
        decide_parameters = dict(revise_payload.get("parameters") or {})
        graph.add_node(
            make_node(
                id="constrain",
                kind="revision_constrain",
                depends_on=["seed"],
                payload={
                    "reads": {
                        "diagnosis": "in.diagnosis",
                        "change_plan": "in.change_plan",
                        "prior_attempts": "in.prior_attempts",
                        "retry_budget": "in.retry_budget",
                    },
                    "writes": {"destination": "acc.revision.constraints"},
                    "parameters": {
                        k: v for k, v in decide_parameters.items() if k == "retry_budget"
                    },
                },
            )
        )
        graph.add_node(
            make_node(
                id="decide",
                kind="revision_decide",
                depends_on=["constrain"],
                payload={
                    "soft_point": "revise_payload",
                    "reads": {"constraints": "acc.revision.constraints"},
                    "writes": {"destination": "acc.revision.decision"},
                    "parameters": decide_parameters,
                },
            )
        )
        graph.add_node(
            make_node(
                id="publish",
                kind="revision_publish",
                depends_on=["decide"],
                payload={
                    "reads": {
                        "constraints": "acc.revision.constraints",
                        "decision": "acc.revision.decision",
                    },
                    "writes": {"destination": "out.strategy_revision"},
                },
            )
        )
        graph.add_node(
            make_node(
                id="validate",
                kind="revision_validate",
                depends_on=["publish"],
                payload={
                    "reads": {"source": "out.strategy_revision"},
                    "writes": {"destination": "acc.revision.validation"},
                    "parameters": {"fail_if_invalid": True},
                },
            )
        )
        order = ["seed", "constrain", "decide", "publish", "validate"]
        for left, right in zip(order, order[1:]):
            graph.add_dependency(
                DependencyEdge(
                    from_node=left,
                    to_node=right,
                    types=["control"],
                    reason="strategy_revision",
                )
            )
        return graph


__all__ = ["StrategyRevisionTemplate"]
