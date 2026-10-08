"""Bounded-retry Agentic Recipe.

Makes attempt, failure classification, retry permission, backoff, and terminal
escalation visible graph behavior. Composes with durable effect reconciliation
rather than blindly redispatches uncertain external effects.
"""

from __future__ import annotations

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)
from mechaharness.stop_contract import StopContract


class BoundedRetryTemplate(GraphTemplate):
    """attempt → classify → permit_retry → backoff, with terminal escalate."""

    name = "bounded_retry"
    version = "1"
    summary = (
        "Visible bounded retry: classify failures, permit retry in code, "
        "apply backoff, escalate when exhausted; defer to effect reconciliation "
        "before redispatches."
    )
    soft_points = (
        SoftPoint(
            name="attempt_kind",
            kind="runner_kind",
            description="Work / dispatch node kind for each attempt",
            default="attempt",
        ),
        SoftPoint(
            name="classify_kind",
            kind="runner_kind",
            description="Failure classification (code or soft model classifier)",
            default="classify",
        ),
        SoftPoint(
            name="permit_kind",
            kind="runner_kind",
            description="Deterministic retry-permission policy node",
            default="permit_retry",
        ),
        SoftPoint(
            name="backoff_kind",
            kind="runner_kind",
            description="Remediation / backoff before the next attempt",
            default="backoff",
        ),
        SoftPoint(
            name="escalate_kind",
            kind="runner_kind",
            description="Terminal escalation when retries are exhausted",
            default="escalate",
        ),
        SoftPoint(
            name="stop_contract",
            kind="budget",
            description="Bound on repeating attempts",
            required=False,
        ),
        SoftPoint(
            name="max_attempts",
            kind="budget",
            description="Max attempt iterations when stop_contract omitted",
            default=3,
        ),
        SoftPoint(
            name="failure_classifier",
            kind="policy",
            description="Soft point for ambiguous failure classification",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = params.inputs
        max_attempts = int(
            bindings.get("max_attempts", inputs.get("max_attempts", 3))
        )
        stop = params.stop_contract or StopContract(
            version="1", max_iterations=max_attempts
        )
        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        attempt = make_node(
            id="attempt",
            kind=str(bindings.get("attempt_kind", "attempt")),
            goal="perform attempt",
            repeating=True,
            stop_contract=stop,
            payload={
                "phase": "attempt",
                "attempt_context_keys": [
                    "prior_failure_classification",
                    "attempt_number",
                    "selected_remediation",
                    "prior_evidence",
                ],
                "requires_effect_reconciliation": True,
            },
        )
        classify = make_node(
            id="classify",
            kind=str(bindings.get("classify_kind", "classify")),
            goal="classify failure",
            depends_on=[attempt.id],
            payload={
                "phase": "classify",
                "classifier": bindings.get("failure_classifier", "deterministic"),
            },
        )
        permit = make_node(
            id="permit_retry",
            kind=str(bindings.get("permit_kind", "permit_retry")),
            goal="decide whether another attempt is permitted",
            depends_on=[classify.id],
            payload={"phase": "permit_retry"},
        )
        backoff = make_node(
            id="backoff",
            kind=str(bindings.get("backoff_kind", "backoff")),
            goal="apply remediation / backoff",
            depends_on=[permit.id],
            payload={"phase": "backoff"},
        )
        escalate = make_node(
            id="escalate",
            kind=str(bindings.get("escalate_kind", "escalate")),
            goal="terminal escalation after exhaustion or non-retryable failure",
            depends_on=[permit.id],
            payload={"phase": "escalate", "terminal": True},
        )
        for node in (attempt, classify, permit, backoff, escalate):
            graph.add_node(node)
        graph.add_dependency(
            DependencyEdge(
                from_node=attempt.id,
                to_node=classify.id,
                types=["data"],
                reason="failure_or_result",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=classify.id,
                to_node=permit.id,
                types=["control"],
                reason="retry_gate",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=permit.id,
                to_node=backoff.id,
                types=["control"],
                reason="retry_permitted",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=permit.id,
                to_node=escalate.id,
                types=["control"],
                reason="retry_exhausted_or_denied",
            )
        )
        return graph
