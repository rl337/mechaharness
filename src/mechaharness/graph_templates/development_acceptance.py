"""DevelopmentAcceptance Agentic Recipe (gastronomic M6 increment 7).

Deterministic completed | needs_guidance | failed gate over contract,
verification, execution, and strategy revision. Optional judge opinion is
advisory only and never replaces host evidence.
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


class DevelopmentAcceptanceTemplate(GraphTemplate):
    """Constrain → decide → publish → validate.

    Catalog id: ``development_acceptance``.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, DevelopmentAcceptanceTemplate,
        ... )
        >>> graph = DevelopmentAcceptanceTemplate().instantiate(GraphTemplateParams(
        ...     goal="Accept multiply change",
        ...     inputs={
        ...         "goal": "Accept multiply change",
        ...         "verification_report": {"version": "1", "status": "ok"},
        ...         "strategy_revision": {
        ...             "disposition": "continue_or_accept",
        ...         },
        ...     },
        ... ))
        >>> graph.template_name
        'development_acceptance'
    """

    name = "development_acceptance"
    version = "1"
    summary = (
        "Deterministic DevelopmentOutcome from host gates; optional judge is "
        "advisory only."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "change_contract": "object",
            "verification_report": "object",
            "change_execution": "object",
            "strategy_revision": "object",
            "coverage": "object",
            "judge_opinion": "object",
        },
        outputs={"development_outcome": "object"},
    )
    soft_points = (
        SoftPoint(
            name="accept_payload",
            kind="task_state",
            description=(
                "Optional parameters for acceptance_decide "
                "(e.g. advisory judge_opinion)"
            ),
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or "accept development outcome")
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
        for key in (
            "change_contract",
            "verification_report",
            "change_execution",
            "strategy_revision",
            "coverage",
            "judge_opinion",
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
        accept_payload = dict(bindings.get("accept_payload") or {})
        decide_parameters = dict(accept_payload.get("parameters") or {})
        constrain_parameters = {
            k: v
            for k, v in decide_parameters.items()
            if k in {"coverage", "judge_opinion"}
        }
        graph.add_node(
            make_node(
                id="constrain",
                kind="acceptance_constrain",
                depends_on=["seed"],
                payload={
                    "reads": {
                        "change_contract": "in.change_contract",
                        "verification_report": "in.verification_report",
                        "change_execution": "in.change_execution",
                        "strategy_revision": "in.strategy_revision",
                        "coverage": "in.coverage",
                        "judge_opinion": "in.judge_opinion",
                    },
                    "writes": {"destination": "acc.acceptance.constraints"},
                    "parameters": constrain_parameters,
                },
            )
        )
        graph.add_node(
            make_node(
                id="decide",
                kind="acceptance_decide",
                depends_on=["constrain"],
                payload={
                    "soft_point": "accept_payload",
                    "reads": {"constraints": "acc.acceptance.constraints"},
                    "writes": {"destination": "acc.acceptance.decision"},
                    "parameters": decide_parameters,
                },
            )
        )
        graph.add_node(
            make_node(
                id="publish",
                kind="acceptance_publish",
                depends_on=["decide"],
                payload={
                    "reads": {
                        "constraints": "acc.acceptance.constraints",
                        "decision": "acc.acceptance.decision",
                    },
                    "writes": {"destination": "out.development_outcome"},
                },
            )
        )
        graph.add_node(
            make_node(
                id="validate",
                kind="acceptance_validate",
                depends_on=["publish"],
                payload={
                    "reads": {"source": "out.development_outcome"},
                    "writes": {"destination": "acc.acceptance.validation"},
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
                    reason="development_acceptance",
                )
            )
        return graph


__all__ = ["DevelopmentAcceptanceTemplate"]
