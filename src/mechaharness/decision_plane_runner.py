"""Graph node runners for the ``decision_plane`` Agentic Recipe."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.decision_plane_runtime import (
    apply_decision_plane_policy,
    build_decision_plane_telemetry,
    evaluate_decision_batch,
    project_decision_state,
    run_decision_plane_policy,
)
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


class ProjectStateRunner(GraphNodeRunner):
    """Build a deliberate projection + facts without model inference (DP-01)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["project_state"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        payload = dict(node.payload)
        raw_context = _mapping(payload.get("raw_context"))
        project_keys = list(payload.get("project_keys") or [])
        facts = _mapping(payload.get("facts"))
        if raw_context and project_keys:
            proj = project_decision_state(
                raw_context,
                project_keys=[str(k) for k in project_keys],
                facts=facts,
            )
        else:
            state = _mapping(payload.get("state_projection"))
            proj = project_decision_state(
                state,
                project_keys=list(state.keys()),
                facts=facts,
            )
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **payload,
                "projection": proj.state,
                "facts": dict(proj.facts),
                "facts_keys": list(proj.facts.keys()),
                "projection_fingerprint": proj.projection_fingerprint,
                "facts_fingerprint": proj.facts_fingerprint,
                "projection_has_secret": "secret" in proj.state,
                "no_model_invocation": True,
                "facts_fingerprint_nonempty": bool(proj.facts_fingerprint),
            },
        )


class AskBatchRunner(GraphNodeRunner):
    """Answer the batched questions via fixture answers or rules backend (DP-02)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["ask_batch"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        project = context.graph.nodes.get("project_state")
        state: dict[str, Any] = {}
        if project is not None:
            state = _mapping(project.payload.get("projection"))
        questions = list(node.payload.get("questions") or [])
        answers = _mapping(
            node.payload.get("fixture_answers")
            or node.payload.get("production_answers")
            or node.payload.get("answers")
        )
        confidence = node.payload.get("confidence")
        conf_val = float(confidence) if confidence is not None else None
        results, invocations = await evaluate_decision_batch(
            questions, answers=answers, state=state
        )
        signals: dict[str, Any] = {}
        rejected: list[str] = []
        for result in results:
            sid = getattr(result.signal, "id", None)
            if sid is None:
                continue
            from mechaharness.decision_plane_runtime import signal_to_public

            signals[str(sid)] = signal_to_public(result.signal)
            if result.rejected:
                rejected.append(str(sid))
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "signals": signals,
                "rejected": rejected,
                "batch_results": [r.model_dump(mode="json") for r in results],
                "batch_invocation_count": invocations,
                "confidence": conf_val,
                "answers_used": answers,
            },
        )


class ApplyPolicyRunner(GraphNodeRunner):
    """Code-owned final action or escalation over ask signals (DP-04/06)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["apply_policy"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        ask = context.graph.nodes.get("ask_batch")
        ask_payload = dict(ask.payload) if ask is not None else {}
        questions = list(ask_payload.get("questions") or node.payload.get("questions") or [])
        from mechaharness.decision_surfaces import DecisionSurfaceResult

        raw_results = list(ask_payload.get("batch_results") or [])
        results = [DecisionSurfaceResult.model_validate(r) for r in raw_results]
        confidence = ask_payload.get("confidence")
        conf_val = float(confidence) if confidence is not None else None
        floor = float(node.payload.get("confidence_floor") or 0.7)
        route = str(node.payload.get("escalation_route") or "host_policy")
        action_qid = str(node.payload.get("action_question_id") or "team")
        invocations = int(ask_payload.get("batch_invocation_count") or 1)
        if results:
            policy = apply_decision_plane_policy(
                results,
                questions=questions,
                confidence=conf_val,
                confidence_floor=floor,
                escalation_route=route,
                action_question_id=action_qid,
                batch_invocation_count=invocations,
            )
        else:
            answers = _mapping(ask_payload.get("answers_used"))
            policy = await run_decision_plane_policy(
                questions=questions,
                answers=answers,
                confidence=conf_val,
                confidence_floor=floor,
                escalation_route=route,
                action_question_id=action_qid,
            )
        dumped = policy.model_dump(mode="json")
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                **dumped,
                "policy": dumped,
            },
        )


class EscalateRunner(GraphNodeRunner):
    """Routable escalation exit — records policy outcome without failing the graph."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["escalate"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        policy = context.graph.nodes.get("apply_policy")
        policy_payload = dict(policy.payload) if policy is not None else {}
        escalate = bool(policy_payload.get("escalate"))
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "escalate": escalate,
                "escalation_reason": policy_payload.get("escalation_reason"),
                "escalation_route": policy_payload.get("escalation_route")
                or node.payload.get("route"),
                "final_action": policy_payload.get("final_action"),
                "taken": escalate,
            },
        )


class ShadowAskRunner(GraphNodeRunner):
    """Non-gating shadow decision path for evaluation (DP-07)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["shadow_ask"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        questions = list(node.payload.get("questions") or [])
        answers = _mapping(node.payload.get("shadow_answers"))
        confidence = node.payload.get("confidence")
        conf_val = float(confidence) if confidence is not None else None
        floor = float(node.payload.get("confidence_floor") or 0.7)
        route = str(node.payload.get("escalation_route") or "host_policy")
        action_qid = str(node.payload.get("action_question_id") or "team")
        policy = await run_decision_plane_policy(
            questions=questions,
            answers=answers,
            confidence=conf_val,
            confidence_floor=floor,
            escalation_route=route,
            action_question_id=action_qid,
        )
        dumped = policy.model_dump(mode="json")
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                **dumped,
                "shadow_policy": dumped,
                "controls_execution": False,
            },
        )


def decision_plane_runners() -> list[GraphNodeRunner]:
    """Default runners for ``decision_plane`` execute walks."""
    return [
        ProjectStateRunner(),
        AskBatchRunner(),
        ApplyPolicyRunner(),
        EscalateRunner(),
        ShadowAskRunner(),
    ]


def telemetry_fields_from_graph(
    *,
    graph_nodes: Mapping[str, GraphNode],
    model_ref: str | None = None,
    latency_ms: float | None = None,
    raw_body: Any = None,
) -> dict[str, Any]:
    """Build observation keys for the telemetry story from executed nodes."""
    project = graph_nodes.get("project_state")
    ask = graph_nodes.get("ask_batch")
    policy_node = graph_nodes.get("apply_policy")
    shadow = graph_nodes.get("shadow_ask")
    questions = list((ask.payload if ask else {}).get("questions") or [])
    from mechaharness.decision_plane_runtime import (
        DecisionPlanePolicyResult,
        DecisionPlaneProjection,
    )

    proj = None
    if project is not None:
        proj = DecisionPlaneProjection(
            state=_mapping(project.payload.get("projection")),
            facts=_mapping(project.payload.get("facts")),
            projection_fingerprint=str(
                project.payload.get("projection_fingerprint") or ""
            ),
            facts_fingerprint=str(project.payload.get("facts_fingerprint") or ""),
        )
    policy = None
    if policy_node is not None and policy_node.payload.get("policy"):
        policy = DecisionPlanePolicyResult.model_validate(policy_node.payload["policy"])
    shadow_cmp = None
    if shadow is not None and policy is not None:
        from mechaharness.decision_plane_runtime import ShadowDecisionComparison

        shadow_policy = DecisionPlanePolicyResult.model_validate(
            shadow.payload.get("shadow_policy") or shadow.payload
        )
        shadow_cmp = ShadowDecisionComparison(
            production=policy,
            shadow=shadow_policy,
            shadow_controls_execution=False,
            agreement=policy.final_action == shadow_policy.final_action,
        )
    tel = build_decision_plane_telemetry(
        questions=questions,
        projection=proj,
        policy=policy,
        shadow=shadow_cmp,
        model_ref=model_ref,
        latency_ms=latency_ms,
        raw_context={"body": raw_body} if raw_body is not None else None,
    )
    dumped = tel.model_dump(mode="json")
    return {
        "has_question_schema_ids": bool(tel.question_schema_ids),
        "has_projection_fingerprint": bool(tel.projection_fingerprint),
        "final_action": tel.final_action,
        "model_ref": tel.model_ref,
        "latency_ms": tel.latency_ms,
        "includes_raw_body": "raw_body" in dumped or "body" in dumped,
        "telemetry": dumped,
    }
