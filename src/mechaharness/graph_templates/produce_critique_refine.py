"""Produce-critique-refine subgraph template.

A producer drafts an artifact; a critic with isolated context (no producer
reasoning by default) returns findings; a bounded refine loop applies them
under an explicit :class:`~mechaharness.stop_contract.StopContract`. Unlike
``verify_repair`` the critique is judgement text, not a deterministic oracle;
unlike ``independent_review`` there is one critic and the findings feed a
refinement loop rather than an aggregate.
"""

from __future__ import annotations

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)
from mechaharness.isolation.isolation_contract import TemplateIOContract
from mechaharness.stop_contract import StopContract


class ProduceCritiqueRefineTemplate(GraphTemplate):
    """Produce → isolated critique → bounded refine → complete.

    Only ``critique_prompt`` and ``max_rounds`` are evolvable soft points; the
    topology, critic isolation, and stop contract are hard structure.

    Node components: ``produce`` / ``critique`` / ``refine`` / ``complete``
    each carry the ``soft_point`` components named in their payload
    ``soft_points``; ``refine`` also carries a ``stop_contract`` component.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, ProduceCritiqueRefineTemplate,
        ... )
        >>> graph = ProduceCritiqueRefineTemplate().instantiate(GraphTemplateParams(
        ...     goal="draft release notes",
        ...     acceptance=["no_unverified_claims"],
        ...     soft_bindings={"max_rounds": 2},
        ... ))
        >>> sorted(graph.nodes)
        ['complete', 'critique', 'produce', 'refine']
        >>> graph.nodes["critique"].payload["omit_producer_reasoning"]
        True
        >>> graph.nodes["refine"].stop_contract["max_iterations"]
        2
    """

    name = "produce_critique_refine"
    version = "1"
    summary = (
        "Produce an artifact, critique it in isolated context, then refine under "
        "a stop contract until the critique is addressed or rounds exhaust."
    )
    io_contract = TemplateIOContract(
        inputs={"goal": "string", "acceptance": "list"},
        outputs={"artifact": "object"},
    )
    soft_points = (
        SoftPoint(
            name="produce_kind",
            kind="runner_kind",
            description="Node kind that drafts the artifact",
            default="produce",
        ),
        SoftPoint(
            name="critique_kind",
            kind="runner_kind",
            description="Node kind that critiques the artifact in isolated context",
            default="critique",
        ),
        SoftPoint(
            name="refine_kind",
            kind="runner_kind",
            description="Node kind for bounded refinement rounds",
            default="refine",
        ),
        SoftPoint(
            name="complete_kind",
            kind="runner_kind",
            description="Terminal node kind after refinement",
            default="complete",
        ),
        SoftPoint(
            name="critique_prompt",
            kind="prompt",
            description="How hard and in what voice the critic judges the artifact",
            default="List concrete defects against the acceptance criteria.",
            evolvable=True,
        ),
        SoftPoint(
            name="max_rounds",
            kind="budget",
            description="Refinement rounds before stopping",
            default=2,
            evolvable=True,
        ),
        SoftPoint(
            name="omit_producer_reasoning",
            kind="policy",
            description="When true, the critic does not see producer reasoning",
            default=True,
        ),
        SoftPoint(
            name="acceptance",
            kind="policy",
            description="Acceptance criteria the critic and completion check",
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        stop = params.stop_contract or StopContract(
            version="1", max_iterations=int(bindings.get("max_rounds", 2))
        )
        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        produce = make_node(
            id="produce",
            kind=str(bindings.get("produce_kind", "produce")),
            goal="draft artifact",
            payload={**params.inputs, "soft_points": ["produce_kind"]},
        )
        critique = make_node(
            id="critique",
            kind=str(bindings.get("critique_kind", "critique")),
            goal="critique artifact in isolated context",
            depends_on=[produce.id],
            payload={
                "isolated_context": True,
                "omit_producer_reasoning": bool(
                    bindings.get("omit_producer_reasoning", True)
                ),
                "artifact_ref": produce.id,
                "critique_prompt": str(
                    bindings.get(
                        "critique_prompt",
                        "List concrete defects against the acceptance criteria.",
                    )
                ),
                "acceptance": list(params.acceptance),
                "soft_points": [
                    "critique_kind",
                    "critique_prompt",
                    "omit_producer_reasoning",
                    "acceptance",
                ],
            },
        )
        refine = make_node(
            id="refine",
            kind=str(bindings.get("refine_kind", "refine")),
            goal="apply critique within bounded rounds",
            depends_on=[critique.id],
            repeating=True,
            stop_contract=stop,
            payload={
                "phase": "refine",
                "critique_ref": critique.id,
                "soft_points": ["refine_kind", "max_rounds"],
            },
        )
        done = make_node(
            id="complete",
            kind=str(bindings.get("complete_kind", "complete")),
            goal="mark complete",
            depends_on=[refine.id],
            payload={"soft_points": ["complete_kind"]},
            acceptance=params.acceptance,
        )
        for node in (produce, critique, refine, done):
            graph.add_node(node)
        graph.add_dependency(
            DependencyEdge(
                from_node=produce.id,
                to_node=critique.id,
                types=["data"],
                reason="artifact_for_critique",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=critique.id,
                to_node=refine.id,
                types=["data"],
                reason="critique_findings",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=refine.id, to_node=done.id, types=["control"], reason="done"
            )
        )
        return graph
