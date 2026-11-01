"""GastronomicComparison Agentic Recipe (post-M6 comparison protocol).

Assembles and validates a comparable trial record for guided_coding vs
gastronomic_guided_development arms. Does not declare winners.
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


class GastronomicComparisonTemplate(GraphTemplate):
    """Assemble → validate a gastronomic trial record.

    Catalog id: ``gastronomic_comparison``.
    """

    name = "gastronomic_comparison"
    version = "1"
    summary = (
        "Assemble and validate a comparable A/B/C/D trial record without "
        "declaring a single-run winner."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "development_outcome": "object",
            "metrics": "object",
            "model": "object",
            "budget": "object",
        },
        outputs={"trial": "object"},
    )
    soft_points = (
        SoftPoint(
            name="compare_payload",
            kind="task_state",
            description="trial_id/arm/recipe_id/suite_id for comparison_assemble",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or "record gastronomic trial")
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
        for key in ("development_outcome", "metrics", "model", "budget"):
            if key in inputs:
                seed_put[f"in.{key}"] = inputs[key]
        graph.add_node(
            make_node(
                id="seed",
                kind="compute",
                payload={"bag_put": seed_put} if seed_put else {},
            )
        )
        compare_payload = dict(bindings.get("compare_payload") or {})
        assemble_parameters = dict(compare_payload.get("parameters") or compare_payload)
        graph.add_node(
            make_node(
                id="assemble",
                kind="comparison_assemble",
                depends_on=["seed"],
                payload={
                    "soft_point": "compare_payload",
                    "reads": {
                        "development_outcome": "in.development_outcome",
                        "metrics": "in.metrics",
                        "model": "in.model",
                        "budget": "in.budget",
                    },
                    "writes": {"destination": "out.trial"},
                    "parameters": assemble_parameters,
                },
            )
        )
        graph.add_node(
            make_node(
                id="validate",
                kind="comparison_validate",
                depends_on=["assemble"],
                payload={
                    "reads": {"source": "out.trial"},
                    "writes": {"destination": "acc.comparison.validation"},
                    "parameters": {"fail_if_invalid": True},
                },
            )
        )
        order = ["seed", "assemble", "validate"]
        for left, right in zip(order, order[1:]):
            graph.add_dependency(
                DependencyEdge(
                    from_node=left,
                    to_node=right,
                    types=["control"],
                    reason="gastronomic_comparison",
                )
            )
        return graph


__all__ = ["GastronomicComparisonTemplate"]
