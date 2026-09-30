"""Independent review subgraph template.

Producer creates an artifact; one or more reviewers receive the artifact and
acceptance contract while omitting producer reasoning by default. Disagreement
is retained at aggregation rather than collapsed early.
"""

from __future__ import annotations

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)


class IndependentReviewTemplate(GraphTemplate):
    """Produce → N isolated reviewers → aggregate (retain disagreement)."""

    name = "independent_review"
    version = "1"
    summary = (
        "Independent review with isolated reviewer context. Reviewers see the "
        "artifact and acceptance contract, not producer chain-of-thought, unless "
        "the client opts in."
    )
    soft_points = (
        SoftPoint(
            name="produce_kind",
            kind="runner_kind",
            description="Producer node kind",
            default="produce",
        ),
        SoftPoint(
            name="review_kind",
            kind="runner_kind",
            description="Reviewer node kind",
            default="review",
        ),
        SoftPoint(
            name="aggregate_kind",
            kind="runner_kind",
            description="Aggregation node kind",
            default="aggregate_reviews",
        ),
        SoftPoint(
            name="reviewer_count",
            kind="budget",
            description="Number of independent reviewers",
            default=1,
        ),
        SoftPoint(
            name="omit_producer_reasoning",
            kind="policy",
            description="When true, reviewers omit producer reasoning",
            default=True,
        ),
        SoftPoint(
            name="acceptance",
            kind="policy",
            description="Acceptance contract passed to reviewers",
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        omit = bindings.get("omit_producer_reasoning", True)
        reviewer_count = int(
            bindings.get("reviewer_count", params.inputs.get("reviewer_count", 1))
        )
        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        produce = make_node(
            id="produce",
            kind=str(bindings.get("produce_kind", "produce")),
            goal="produce artifact",
            payload=dict(params.inputs),
        )
        graph.add_node(produce)
        review_ids: list[str] = []
        for i in range(max(1, reviewer_count)):
            rid = f"review_{i}"
            node = make_node(
                id=rid,
                kind=str(bindings.get("review_kind", "review")),
                goal=f"independent review {i}",
                depends_on=[produce.id],
                payload={
                    "isolated_context": True,
                    "omit_producer_reasoning": bool(omit),
                    "artifact_ref": "produce",
                    "acceptance": list(params.acceptance),
                },
            )
            graph.add_node(node)
            graph.add_dependency(
                DependencyEdge(
                    from_node=produce.id,
                    to_node=rid,
                    types=["data"],
                    reason="review_artifact_only",
                )
            )
            review_ids.append(rid)
        aggregate = make_node(
            id="aggregate_reviews",
            kind=str(bindings.get("aggregate_kind", "aggregate_reviews")),
            goal="retain disagreement",
            depends_on=review_ids,
            payload={"retain_disagreement": True},
            acceptance=params.acceptance,
        )
        graph.add_node(aggregate)
        for rid in review_ids:
            graph.add_dependency(
                DependencyEdge(
                    from_node=rid,
                    to_node=aggregate.id,
                    types=["data"],
                    reason="review_result",
                )
            )
        return graph
