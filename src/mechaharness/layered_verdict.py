"""Paired task-success and harness-fidelity scores.

A correct file can hide a dropped tool error, and a faithful harness can still
deliver a wrong answer. Missing observations stay ``unknown``; they are not
rewritten as a pass or as an infrastructure failure.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from mechaharness.eval_evidence import Claim
from mechaharness.evaluation_outcome import EvaluationOutcome

LayerStatus = Literal["pass", "fail", "unknown", "unscored"]
Attribution = Literal["none", "hypothesis", "caller_asserted"]


class LayeredEvaluation(BaseModel):
    """Typed report over existing evaluation claims; supplied claims are not observations."""

    task: Claim
    harness: Claim
    outcome: EvaluationOutcome
    causal_support: Claim | None = None

    def report(self) -> dict[str, Any]:
        unscored = not self.outcome.task_scored
        task_status = self.task.status if not unscored else "unscored"
        harness_status = self.harness.status if not unscored else "unscored"
        attribution: Attribution = "none"
        if task_status == "fail" and harness_status == "fail":
            attribution = (
                "caller_asserted"
                if self.causal_support is not None and self.causal_support.status == "pass"
                else "hypothesis"
            )
        return {
            "task": task_status,
            "harness": harness_status,
            "clean": task_status == "pass" and harness_status == "pass",
            "infrastructure_failure": self.outcome.kind == "execution_failure",
            "attribution": attribution,
            "evidence_origin": "caller_supplied",
        }


def score_layers(
    *,
    task: Literal["pass", "fail"],
    harness: Literal["pass", "fail"] | None = None,
    harness_observed: bool = True,
    infrastructure_failure: bool = False,
    trace_supports_cause: bool = False,
) -> dict[str, Any]:
    """Combine caller-supplied task and harness verdicts for one run.

    The caller evaluates task success and trace fidelity before calling this
    helper. Missing harness observations yield ``unknown``; an infrastructure
    failure leaves both layers ``unscored``. A run is clean only if both pass.
    ``attribution='caller_asserted'`` records the caller's ``trace_supports_cause``
    assertion when both fail; this helper does not inspect causal evidence.

    Example:
        >>> lucky = score_layers(task="pass", harness="fail")
        >>> (lucky["task"], lucky["harness"], lucky["clean"])
        ('pass', 'fail', False)
        >>> score_layers(task="pass")["harness"]
        'unknown'
        >>> score_layers(task="fail", harness="fail")["attribution"]
        'hypothesis'
    """
    outcome = EvaluationOutcome(
        kind="execution_failure"
        if infrastructure_failure
        else ("success" if task == "pass" else "task_failure")
    )
    return LayeredEvaluation(
        task=Claim(id="task", statement="task succeeded", status=task),
        harness=Claim(
            id="harness",
            statement="harness fidelity passed",
            status=harness if harness_observed and harness is not None else "unknown",
        ),
        outcome=outcome,
        causal_support=(
            Claim(id="cause", statement="caller asserts causal trace support", status="pass")
            if trace_supports_cause
            else None
        ),
    ).report()
