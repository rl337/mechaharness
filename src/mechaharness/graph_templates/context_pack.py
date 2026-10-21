"""RAG context-pack Agentic Recipe: retrieve → pack within token budget.

Hosts bind :class:`~mechaharness.rag.RagRetriever` (production or
:class:`~mechaharness.rag.FixtureRagRetriever`). Packing is code-owned via
:func:`~mechaharness.decision_plane_runtime.assemble_context_within_budget`.
"""

from __future__ import annotations

from typing import Any

from mechaharness.graph import ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)


class ContextPackTemplate(GraphTemplate):
    """retrieve → pack: scored RAG hits into a fixed token window.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     ContextPackTemplate, GraphTemplateParams,
        ... )
        >>> graph = ContextPackTemplate().instantiate(GraphTemplateParams(
        ...     goal="pack",
        ...     soft_bindings={
        ...         "query": "revenue growth",
        ...         "token_budget": 120,
        ...     },
        ... ))
        >>> graph.template_name
        'context_pack'
        >>> list(graph.nodes)
        ['retrieve', 'pack']
    """

    name = "context_pack"
    version = "1"
    summary = (
        "Retrieve RAG candidates via host RagRetriever, then deterministically "
        "pack them into a token budget with trust/relevance/freshness floors."
    )
    soft_points = (
        SoftPoint(
            name="retrieve_kind",
            kind="runner_kind",
            description="Node kind that calls RagRetriever.retrieve",
            default="rag_retrieve",
        ),
        SoftPoint(
            name="pack_kind",
            kind="runner_kind",
            description="Node kind that packs scored candidates into the budget",
            default="rag_pack",
        ),
        SoftPoint(
            name="query",
            kind="task_state",
            description="Retrieval query string",
            required=True,
        ),
        SoftPoint(
            name="token_budget",
            kind="policy",
            description="Max tokens for the packed context window",
            default=256,
        ),
        SoftPoint(
            name="min_relevance",
            kind="policy",
            description="Minimum relevance score to keep a candidate",
            default=0.0,
        ),
        SoftPoint(
            name="min_trust",
            kind="policy",
            description="Minimum trust score to keep a candidate",
            default=0.0,
        ),
        SoftPoint(
            name="min_freshness",
            kind="policy",
            description="Minimum freshness score to keep a candidate",
            default=0.0,
        ),
        SoftPoint(
            name="retrieve_limit",
            kind="policy",
            description="Max candidates to request from the retriever",
            default=32,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = params.inputs
        query = bindings.get("query", inputs.get("query"))
        if not query:
            raise ValueError("context_pack requires soft_bindings/inputs query")
        retrieve_kind = str(bindings.get("retrieve_kind", "rag_retrieve"))
        pack_kind = str(bindings.get("pack_kind", "rag_pack"))
        token_budget = int(bindings.get("token_budget", inputs.get("token_budget", 256)))
        min_relevance = float(
            bindings.get("min_relevance", inputs.get("min_relevance", 0.0))
        )
        min_trust = float(bindings.get("min_trust", inputs.get("min_trust", 0.0)))
        min_freshness = float(
            bindings.get("min_freshness", inputs.get("min_freshness", 0.0))
        )
        retrieve_limit = int(
            bindings.get("retrieve_limit", inputs.get("retrieve_limit", 32))
        )
        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        retrieve = make_node(
            id="retrieve",
            kind=retrieve_kind,
            goal=f"retrieve for {query!r}",
            payload={
                "phase": "retrieve",
                "query": str(query),
                "limit": retrieve_limit,
            },
        )
        graph.add_node(retrieve)
        pack_payload: dict[str, Any] = {
            "phase": "pack",
            "token_budget": token_budget,
            "min_relevance": min_relevance,
            "min_trust": min_trust,
            "min_freshness": min_freshness,
        }
        graph.add_node(
            make_node(
                id="pack",
                kind=pack_kind,
                goal="pack context within budget",
                depends_on=[retrieve.id],
                payload=pack_payload,
            )
        )
        return graph
