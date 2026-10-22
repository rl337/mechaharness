"""Graph node runners for the ``safety_eval`` Agentic Recipe."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


class SafetyProduceRunner(GraphNodeRunner):
    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["produce"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        payload = dict(node.payload)
        scenario = _mapping(payload.get("scenario"))
        if not scenario:
            scenario = {
                "class": str(
                    (payload.get("scenario_classes") or ["prompt_injection_in_tool_output"])[
                        0
                    ]
                ),
                "id": "fixture-1",
            }
        outcome = payload.get("sut_outcome") or {
            "action": "refused",
            "authorized": True,
        }
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **payload,
                "scenario": scenario,
                "sut_outcome": outcome,
                "producer_reasoning": payload.get("producer_reasoning"),
            },
        )


class SafetyReviewRunner(GraphNodeRunner):
    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["review"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        produce = context.graph.nodes.get("produce")
        produce_payload = dict(produce.payload) if produce else {}
        omit = bool(node.payload.get("omit_producer_reasoning", True))
        verdict = produce_payload.get("review_verdict") or node.payload.get(
            "review_verdict"
        ) or {
            "safe": True,
            "severity": "info",
            "notes": "fixture",
        }
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "verdict": verdict,
                "omit_producer_reasoning": omit,
                "isolated_context": True,
                "saw_producer_reasoning": False if omit else (
                    produce_payload.get("producer_reasoning") is not None
                ),
                "sut_outcome": produce_payload.get("sut_outcome"),
                "scenario": produce_payload.get("scenario"),
            },
        )


class SafetyScoreRunner(GraphNodeRunner):
    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["score"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        review = context.graph.nodes.get("review")
        produce = context.graph.nodes.get("produce")
        review_payload = dict(review.payload) if review else {}
        produce_payload = dict(produce.payload) if produce else {}
        verdict = _mapping(review_payload.get("verdict"))
        severity = str(verdict.get("severity") or "info")
        outcome = "pass" if verdict.get("safe", True) else "fail"
        report = {
            "outcome": outcome,
            "severity": severity,
            "context": produce_payload.get("scenario") or {},
            "model_version": node.payload.get("model_version")
            or produce_payload.get("model_version"),
            "recipe_version": node.payload.get("recipe_version") or "1",
        }
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "safety_report": report,
                "deterministic": True,
                **report,
            },
        )


def safety_eval_runners() -> list[GraphNodeRunner]:
    return [SafetyProduceRunner(), SafetyReviewRunner(), SafetyScoreRunner()]
