"""Paired task-success and harness-fidelity scores.

A correct file can hide a dropped tool error, and a faithful harness can still
deliver a wrong answer. Missing observations stay ``unknown``; they are not
rewritten as a pass or as an infrastructure failure.
"""

from __future__ import annotations

from typing import Any, Literal

LayerStatus = Literal["pass", "fail", "unknown", "unscored"]
Attribution = Literal["none", "hypothesis", "observed"]


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
    ``attribution='observed'`` records the caller's ``trace_supports_cause``
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
    if infrastructure_failure:
        return {
            "task": "unscored",
            "harness": "unscored",
            "clean": False,
            "infrastructure_failure": True,
            "attribution": "none",
        }
    harness_status: LayerStatus = (
        harness if harness_observed and harness is not None else "unknown"
    )
    clean = task == "pass" and harness_status == "pass"
    if task == "fail" and harness_status == "fail":
        attribution: Attribution = "observed" if trace_supports_cause else "hypothesis"
    else:
        attribution = "none"
    return {
        "task": task,
        "harness": harness_status,
        "clean": clean,
        "infrastructure_failure": False,
        "attribution": attribution,
    }
