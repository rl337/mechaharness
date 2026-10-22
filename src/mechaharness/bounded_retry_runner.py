"""Graph node runners for the ``bounded_retry`` Agentic Recipe."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _stop_max_iterations(node: GraphNode) -> int:
    stop = node.stop_contract
    if isinstance(stop, Mapping):
        if stop.get("max_iterations") is not None:
            return int(stop["max_iterations"])
        return int(node.payload.get("max_attempts") or 3)
    value = getattr(stop, "max_iterations", None) if stop is not None else None
    if value is not None:
        return int(value)
    return int(node.payload.get("max_attempts") or 3)


class AttemptRunner(GraphNodeRunner):
    """Perform fixture attempts until success or budget (embedded loop)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["attempt"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        payload = dict(node.payload)
        max_attempts = _stop_max_iterations(node)
        succeed_on = payload.get("succeed_on_attempt")
        if succeed_on is None:
            succeed_on = max_attempts  # last attempt succeeds by default
        succeed_on = int(succeed_on)
        failure_class = str(payload.get("failure_class") or "transient")
        attempt_count = 0
        succeeded = False
        last_error = None
        while attempt_count < max_attempts:
            attempt_count += 1
            if attempt_count >= succeed_on:
                succeeded = True
                last_error = None
                break
            last_error = failure_class
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **payload,
                "attempt_count": attempt_count,
                "attempt_succeeded": succeeded,
                "last_error": last_error,
                "requires_effect_reconciliation": bool(
                    payload.get("requires_effect_reconciliation", True)
                ),
            },
        )


class ClassifyRunner(GraphNodeRunner):
    """Classify the last attempt failure (fixture / deterministic)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["classify"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        attempt = context.graph.nodes.get("attempt")
        attempt_payload = dict(attempt.payload) if attempt else {}
        if attempt_payload.get("attempt_succeeded"):
            classification = "success"
            retryable = False
        else:
            classification = str(
                node.payload.get("classifier_result")
                or attempt_payload.get("last_error")
                or "transient"
            )
            retryable = classification in {
                "transient",
                "retryable",
                "timeout",
                "unavailable",
            }
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "classification": classification,
                "retryable": retryable,
                "attempt_count": int(attempt_payload.get("attempt_count") or 0),
                "attempt_succeeded": bool(attempt_payload.get("attempt_succeeded")),
            },
        )


class PermitRetryRunner(GraphNodeRunner):
    """Code-owned retry permission after classification."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["permit_retry"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        classify = context.graph.nodes.get("classify")
        attempt = context.graph.nodes.get("attempt")
        classify_payload = dict(classify.payload) if classify else {}
        attempt_payload = dict(attempt.payload) if attempt else {}
        max_attempts = _stop_max_iterations(attempt) if attempt else 3
        attempt_count = int(
            classify_payload.get("attempt_count")
            or attempt_payload.get("attempt_count")
            or 0
        )
        succeeded = bool(classify_payload.get("attempt_succeeded"))
        retryable = bool(classify_payload.get("retryable"))
        # After embedded attempt loop finished, another graph-level retry is not
        # scheduled — permit records whether backoff vs escalate is the exit.
        if succeeded:
            permitted = False
            reason = "succeeded"
        elif retryable and attempt_count < max_attempts:
            permitted = True
            reason = "retryable_under_budget"
        else:
            permitted = False
            reason = "exhausted_or_non_retryable"
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "retry_permitted": permitted,
                "permit_reason": reason,
                "attempt_count": attempt_count,
                "attempt_succeeded": succeeded,
                "classification": classify_payload.get("classification"),
            },
        )


class BackoffRunner(GraphNodeRunner):
    """Record backoff when retry was permitted (non-gating stamp)."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["backoff"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        permit = context.graph.nodes.get("permit_retry")
        permitted = bool(permit.payload.get("retry_permitted")) if permit else False
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "backoff_applied": permitted,
                "taken": permitted,
            },
        )


class RetryEscalateRunner(GraphNodeRunner):
    """Terminal escalation when retries exhausted or denied."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["escalate"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        permit = context.graph.nodes.get("permit_retry")
        permit_payload = dict(permit.payload) if permit else {}
        succeeded = bool(permit_payload.get("attempt_succeeded"))
        permitted = bool(permit_payload.get("retry_permitted"))
        escalated = not succeeded and not permitted
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "escalated": escalated,
                "taken": escalated,
                "attempt_count": int(permit_payload.get("attempt_count") or 0),
                "attempt_succeeded": succeeded,
            },
        )


def bounded_retry_runners() -> list[GraphNodeRunner]:
    return [
        AttemptRunner(),
        ClassifyRunner(),
        PermitRetryRunner(),
        BackoffRunner(),
        RetryEscalateRunner(),
    ]
