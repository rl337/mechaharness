"""Typed decision-plane Agentic Recipe.

Project structured state, ask a batch of bounded questions in one inference
step, keep deterministic facts in code, apply policy in code, and escalate
when confidence is below the configured floor.
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


class DecisionPlaneTemplate(GraphTemplate):
    """project_state → ask_batch → apply_policy (+ escalate; optional shadow)."""

    name = "decision_plane"
    version = "1"
    summary = (
        "Typed, batched decision plane: structured state projection, "
        "deterministic facts, model evidence, code-owned final policy, "
        "and routable escalation on low confidence."
    )
    soft_points = (
        SoftPoint(
            name="project_kind",
            kind="runner_kind",
            description="Node kind that builds the deliberate state projection",
            default="project_state",
        ),
        SoftPoint(
            name="ask_kind",
            kind="runner_kind",
            description="Node kind for one batched decision inference call",
            default="ask_batch",
        ),
        SoftPoint(
            name="policy_kind",
            kind="runner_kind",
            description="Deterministic policy node over typed signals + facts",
            default="apply_policy",
        ),
        SoftPoint(
            name="escalate_kind",
            kind="runner_kind",
            description="Routable escalation exit (model/recipe/human/fallback)",
            default="escalate",
        ),
        SoftPoint(
            name="shadow_ask_kind",
            kind="runner_kind",
            description="Non-gating shadow decision path for evaluation",
            default="shadow_ask",
        ),
        SoftPoint(
            name="confidence_floor",
            kind="policy",
            description="Minimum confidence before accepting small-model answers",
            default=0.7,
        ),
        SoftPoint(
            name="shadow_mode",
            kind="policy",
            description="When true, add a shadow ask that does not gate policy",
            default=False,
        ),
        SoftPoint(
            name="questions",
            kind="task_state",
            description="Batched typed questions with domains / allowed actions "
            "(via params.inputs or soft_bindings)",
        ),
        SoftPoint(
            name="state_projection",
            kind="task_state",
            description="Deliberate structured projection (not full graph context)",
        ),
        SoftPoint(
            name="facts",
            kind="task_state",
            description="Deterministic facts computed outside inference",
            default={},
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = params.inputs
        questions = list(
            bindings.get("questions")
            if "questions" in bindings
            else inputs.get("questions")
            or []
        )
        if not questions:
            raise ValueError("decision_plane requires a non-empty questions batch")
        projection = dict(
            bindings.get("state_projection")
            if "state_projection" in bindings
            else inputs.get("state_projection")
            or {}
        )
        facts = dict(
            bindings.get("facts")
            if "facts" in bindings
            else inputs.get("facts")
            or {}
        )
        confidence_floor = float(
            bindings.get(
                "confidence_floor",
                inputs.get("confidence_floor", 0.7),
            )
        )
        shadow_mode = bool(
            bindings.get("shadow_mode", inputs.get("shadow_mode", False))
        )

        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        project = make_node(
            id="project_state",
            kind=str(bindings.get("project_kind", "project_state")),
            goal="project decision state",
            payload={
                "phase": "project_state",
                "state_projection": projection,
                "facts": facts,
            },
        )
        ask = make_node(
            id="ask_batch",
            kind=str(bindings.get("ask_kind", "ask_batch")),
            goal="answer batched decision questions",
            depends_on=[project.id],
            payload={
                "phase": "ask_batch",
                "questions": questions,
                "allowed_action_envelopes": _envelopes(questions),
                "confidence_floor": confidence_floor,
                "inference_mode": "batch",
            },
        )
        policy = make_node(
            id="apply_policy",
            kind=str(bindings.get("policy_kind", "apply_policy")),
            goal="deterministic final policy over signals and facts",
            depends_on=[ask.id],
            payload={
                "phase": "apply_policy",
                "facts_ref": "project_state",
                "signals_ref": "ask_batch",
                "confidence_floor": confidence_floor,
            },
        )
        escalate = make_node(
            id="escalate",
            kind=str(bindings.get("escalate_kind", "escalate")),
            goal="routable escalation when confidence or validity fails",
            depends_on=[policy.id],
            payload={
                "phase": "escalate",
                "route": bindings.get("escalation_route", "host_policy"),
            },
        )
        for node in (project, ask, policy, escalate):
            graph.add_node(node)
        graph.add_dependency(
            DependencyEdge(
                from_node=project.id,
                to_node=ask.id,
                types=["data"],
                reason="projection",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=ask.id,
                to_node=policy.id,
                types=["data"],
                reason="signals",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=policy.id,
                to_node=escalate.id,
                types=["control"],
                reason="escalation_exit",
            )
        )
        if shadow_mode:
            shadow = make_node(
                id="shadow_ask",
                kind=str(bindings.get("shadow_ask_kind", "shadow_ask")),
                goal="shadow decision path (non-gating)",
                depends_on=[project.id],
                payload={
                    "phase": "shadow_ask",
                    "questions": questions,
                    "confidence_floor": confidence_floor,
                    "controls_execution": False,
                },
            )
            graph.add_node(shadow)
            graph.add_dependency(
                DependencyEdge(
                    from_node=project.id,
                    to_node=shadow.id,
                    types=["data"],
                    reason="shadow_projection",
                )
            )
        return graph


def _envelopes(questions: list[Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for raw in questions:
        if not isinstance(raw, dict):
            continue
        qid = str(raw.get("id") or "")
        allowed = raw.get("allowed_actions")
        if qid and isinstance(allowed, list):
            out[qid] = [str(a) for a in allowed]
    return out
