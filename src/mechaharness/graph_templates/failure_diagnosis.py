"""FailureDiagnosis Agentic Recipe (gastronomic M6 increment 5).

Classifies host-observed VerificationReport (and optional execution) failures
into a typed Diagnosis with a distinct next experiment. Does not mutate the
workspace and does not invent model-only evidence.
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
from mechaharness.isolation.isolation_contract import TemplateIOContract


class FailureDiagnosisTemplate(GraphTemplate):
    """Constrain → classify → publish → validate.

    Catalog id: ``failure_diagnosis``.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, FailureDiagnosisTemplate,
        ... )
        >>> graph = FailureDiagnosisTemplate().instantiate(GraphTemplateParams(
        ...     goal="Diagnose multiply verify failure",
        ...     inputs={
        ...         "goal": "Diagnose multiply verify failure",
        ...         "verification_report": {
        ...             "version": "1",
        ...             "status": "failed",
        ...             "failures": ["pytest exit 1"],
        ...         },
        ...     },
        ... ))
        >>> graph.template_name
        'failure_diagnosis'
    """

    name = "failure_diagnosis"
    version = "1"
    summary = (
        "Classify host-observed verification/execution failures into a typed "
        "Diagnosis with evidence-linked next experiment."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "verification_report": "object",
            "change_execution": "object",
            "prior_attempts": "object",
        },
        outputs={"diagnosis": "object"},
    )
    soft_points = (
        SoftPoint(
            name="diagnose_payload",
            kind="task_state",
            description="Optional parameters for diagnosis_classify",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or "diagnose verification failure")
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
        for key in ("verification_report", "change_execution", "prior_attempts"):
            if key in inputs:
                seed_put[f"in.{key}"] = inputs[key]
        graph.add_node(
            make_node(
                id="seed",
                kind="compute",
                payload={"bag_put": seed_put} if seed_put else {},
            )
        )
        diagnose_payload = dict(bindings.get("diagnose_payload") or {})
        classify_parameters = dict(diagnose_payload.get("parameters") or {})
        graph.add_node(
            make_node(
                id="constrain",
                kind="diagnosis_constrain",
                depends_on=["seed"],
                payload={
                    "reads": {
                        "verification_report": "in.verification_report",
                        "execution": "in.change_execution",
                        "prior_attempts": "in.prior_attempts",
                    },
                    "writes": {"destination": "acc.diagnosis.constraints"},
                },
            )
        )
        graph.add_node(
            make_node(
                id="classify",
                kind="diagnosis_classify",
                depends_on=["constrain"],
                payload={
                    "soft_point": "diagnose_payload",
                    "reads": {"constraints": "acc.diagnosis.constraints"},
                    "writes": {"destination": "acc.diagnosis.classification"},
                    "parameters": classify_parameters,
                },
            )
        )
        graph.add_node(
            make_node(
                id="publish",
                kind="diagnosis_publish",
                depends_on=["classify"],
                payload={
                    "reads": {
                        "constraints": "acc.diagnosis.constraints",
                        "classification": "acc.diagnosis.classification",
                    },
                    "writes": {"destination": "out.diagnosis"},
                },
            )
        )
        graph.add_node(
            make_node(
                id="validate",
                kind="diagnosis_validate",
                depends_on=["publish"],
                payload={
                    "reads": {"source": "out.diagnosis"},
                    "writes": {"destination": "acc.diagnosis.validation"},
                    "parameters": {"fail_if_invalid": True},
                },
            )
        )
        order = ["seed", "constrain", "classify", "publish", "validate"]
        for left, right in zip(order, order[1:]):
            graph.add_dependency(
                DependencyEdge(
                    from_node=left,
                    to_node=right,
                    types=["control"],
                    reason="failure_diagnosis",
                )
            )
        return graph


__all__ = ["FailureDiagnosisTemplate"]
