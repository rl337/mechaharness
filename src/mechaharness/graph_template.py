"""Parameterized graph templates owned by MechaHarness.

June (and other hosts) instantiate templates with host bindings; they do not
own or fork template definitions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode
from mechaharness.stop_contract import StopContract


class GraphTemplateParams(BaseModel):
    """Host bindings applied when instantiating a template."""

    model_config = ConfigDict(extra="allow")

    goal: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    branch_payloads: list[dict[str, Any]] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    stop_contract: StopContract | None = None
    envelope_ref: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class GraphTemplate(ABC):
    """Reusable parameterized subgraph factory."""

    name: str = "template"
    version: str = "1"

    @abstractmethod
    def instantiate(self, params: GraphTemplateParams) -> ExecutionGraph:
        """Build a concrete :class:`~mechaharness.graph.ExecutionGraph`."""


class GraphTemplateRegistry:
    """Library + host-merged template map (Config hook)."""

    def __init__(self, templates: Sequence[GraphTemplate] | None = None) -> None:
        self._by_name: dict[str, GraphTemplate] = {}
        for template in templates or []:
            self.register(template)

    def register(self, template: GraphTemplate) -> None:
        self._by_name[template.name] = template

    def get(self, name: str) -> GraphTemplate | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return sorted(self._by_name)

    def merge(self, other: GraphTemplateRegistry) -> GraphTemplateRegistry:
        for name in other.names():
            template = other.get(name)
            if template is not None:
                self.register(template)
        return self


def _node(
    *,
    id: str | None = None,
    kind: str,
    goal: str = "",
    depends_on: Sequence[str] | None = None,
    payload: Mapping[str, Any] | None = None,
    write_scopes: Sequence[str] | None = None,
    repeating: bool = False,
    stop_contract: StopContract | None = None,
    acceptance: Sequence[str] | None = None,
) -> GraphNode:
    return GraphNode(
        id=id or str(uuid4()),
        kind=kind,
        goal=goal,
        depends_on=list(depends_on or []),
        payload=dict(payload or {}),
        write_scopes=list(write_scopes or []),
        repeating=repeating,
        stop_contract=stop_contract.model_dump(mode="json") if stop_contract else None,
        acceptance=list(acceptance or []),
    )


class FanOutAggregateTemplate(GraphTemplate):
    """Produce branches then aggregate (uses hierarchical fan-in at reduce time)."""

    name = "fan_out_aggregate"
    version = "1"

    def instantiate(self, params: GraphTemplateParams) -> ExecutionGraph:
        graph = ExecutionGraph(goal=params.goal or "fan_out_aggregate", version=self.version)
        plan = _node(id="plan", kind="plan", goal="plan fan-out", payload={"phase": "plan"})
        graph.add_node(plan)
        branch_ids: list[str] = []
        payloads = params.branch_payloads or [{"index": 0}]
        for i, branch in enumerate(payloads):
            nid = f"branch_{i}"
            node = _node(
                id=nid,
                kind="branch",
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
        reduce = _node(
            id="reduce",
            kind="reduce",
            goal="aggregate branches",
            depends_on=branch_ids,
            payload={"fan_in_budget": int(params.inputs.get("fan_in_budget", 8))},
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


class VerifyRepairTemplate(GraphTemplate):
    """Produce → verify → optional bounded repair loop."""

    name = "verify_repair"
    version = "1"

    def instantiate(self, params: GraphTemplateParams) -> ExecutionGraph:
        stop = params.stop_contract or StopContract(version="1", max_iterations=3)
        graph = ExecutionGraph(goal=params.goal or "verify_repair", version=self.version)
        produce = _node(
            id="produce",
            kind="produce",
            goal="produce artifact",
            payload=dict(params.inputs),
        )
        verify = _node(
            id="verify",
            kind="verify",
            goal="verify artifact",
            depends_on=[produce.id],
            payload={"phase": "verify"},
            acceptance=params.acceptance,
        )
        repair = _node(
            id="repair",
            kind="repair",
            goal="bounded repair",
            depends_on=[verify.id],
            repeating=True,
            stop_contract=stop,
            payload={"phase": "repair"},
        )
        done = _node(
            id="complete",
            kind="complete",
            goal="mark complete",
            depends_on=[repair.id],
            acceptance=params.acceptance,
        )
        for node in (produce, verify, repair, done):
            graph.add_node(node)
        graph.add_dependency(
            DependencyEdge(from_node=produce.id, to_node=verify.id, types=["data"], reason="artifact")
        )
        graph.add_dependency(
            DependencyEdge(from_node=verify.id, to_node=repair.id, types=["control"], reason="repair_gate")
        )
        graph.add_dependency(
            DependencyEdge(from_node=repair.id, to_node=done.id, types=["control"], reason="done")
        )
        return graph


class IndependentReviewTemplate(GraphTemplate):
    """Producer then isolated reviewer(s) — reviewers omit producer reasoning by default."""

    name = "independent_review"
    version = "1"

    def instantiate(self, params: GraphTemplateParams) -> ExecutionGraph:
        graph = ExecutionGraph(goal=params.goal or "independent_review", version=self.version)
        produce = _node(
            id="produce",
            kind="produce",
            goal="produce artifact",
            payload=dict(params.inputs),
        )
        graph.add_node(produce)
        reviewer_count = int(params.inputs.get("reviewer_count", 1))
        review_ids: list[str] = []
        for i in range(max(1, reviewer_count)):
            rid = f"review_{i}"
            node = _node(
                id=rid,
                kind="review",
                goal=f"independent review {i}",
                depends_on=[produce.id],
                payload={
                    "isolated_context": True,
                    "omit_producer_reasoning": True,
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
        aggregate = _node(
            id="aggregate_reviews",
            kind="aggregate_reviews",
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


class EnvironmentRepairTemplate(GraphTemplate):
    """Bounded subgraph to repair missing environment capabilities."""

    name = "environment_repair"
    version = "1"

    def instantiate(self, params: GraphTemplateParams) -> ExecutionGraph:
        stop = params.stop_contract or StopContract(version="1", max_iterations=2)
        graph = ExecutionGraph(goal=params.goal or "environment_repair", version=self.version)
        diagnose = _node(
            id="diagnose",
            kind="env_diagnose",
            goal="diagnose environment",
            payload=dict(params.inputs),
        )
        repair = _node(
            id="repair_env",
            kind="env_repair",
            goal="repair environment",
            depends_on=[diagnose.id],
            repeating=True,
            stop_contract=stop,
            payload={"phase": "repair"},
        )
        recheck = _node(
            id="recheck",
            kind="env_recheck",
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


def default_graph_templates() -> GraphTemplateRegistry:
    """Library-owned templates hosts merge via Config."""
    return GraphTemplateRegistry(
        [
            FanOutAggregateTemplate(),
            VerifyRepairTemplate(),
            IndependentReviewTemplate(),
            EnvironmentRepairTemplate(),
        ]
    )


class SubgraphNodeRunner:
    """Marker helpers for nesting child graphs under a parent node."""

    KIND = "subgraph"

    @staticmethod
    def embed(child: ExecutionGraph, *, parent_node_id: str) -> GraphNode:
        return GraphNode(
            id=parent_node_id,
            kind=SubgraphNodeRunner.KIND,
            goal=child.goal,
            subgraph=child.checkpoint(),
            payload={"child_graph_id": child.id, "child_version": child.version},
        )
