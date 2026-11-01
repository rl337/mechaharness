"""Deterministic Diagnosis hard-node runners (gastronomic M6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.discovery_hard_nodes import (
    DiscoveryHardNodeError,
    _as_mapping,
    _payload_section,
    _read_path,
)
from mechaharness.failure_diagnosis import (
    assemble_diagnosis,
    classify_failure_evidence,
    extract_diagnosis_constraints,
    validate_diagnosis,
)
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.walk_bag import WalkBag, WalkBagPathError, WalkBagSerializeError

DIAGNOSIS_HARD_KINDS: tuple[str, ...] = (
    "diagnosis_constrain",
    "diagnosis_classify",
    "diagnosis_publish",
    "diagnosis_validate",
)


class DiagnosisHardNodeRunner(GraphNodeRunner):
    """Run failure-diagnosis hard-node kinds with atomic bag writes."""

    def __init__(self, kinds: Sequence[str] | None = None) -> None:
        selected = list(kinds) if kinds is not None else list(DIAGNOSIS_HARD_KINDS)
        unknown = [k for k in selected if k not in DIAGNOSIS_HARD_KINDS]
        if unknown:
            raise ValueError(f"unknown diagnosis hard-node kinds: {unknown}")
        if not selected:
            raise ValueError("DiagnosisHardNodeRunner requires at least one kind")
        self._kinds = selected

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        payload = node.payload if isinstance(node.payload, Mapping) else {}
        try:
            reads = _payload_section(payload, "reads")
            writes = _payload_section(payload, "writes")
            parameters = _payload_section(payload, "parameters")
            result = self._dispatch(
                str(node.kind),
                bag=context.bag,
                reads=reads,
                parameters=parameters,
            )
            dest = writes.get("destination")
            if not isinstance(dest, str) or not dest.strip():
                raise DiscoveryHardNodeError("writes.destination is required")
            batch = context.bag.staged_writes()
            batch.put(dest, result)
            batch.commit()
            return NodeOutcome(status=NodeStatus.SUCCEEDED)
        except (DiscoveryHardNodeError, WalkBagPathError, WalkBagSerializeError) as exc:
            return NodeOutcome(status=NodeStatus.FAILED, error=str(exc))

    def _dispatch(
        self,
        kind: str,
        *,
        bag: WalkBag,
        reads: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> Any:
        if kind == "diagnosis_constrain":
            report_path = str(reads.get("verification_report") or "in.verification_report")
            execution_path = str(reads.get("execution") or "in.change_execution")
            prior_path = reads.get("prior_attempts")
            report_raw = _read_path(bag, report_path, required=False)
            execution_raw = _read_path(bag, execution_path, required=False)
            report = (
                _as_mapping(report_raw, label="verification_report")
                if isinstance(report_raw, Mapping)
                else {}
            )
            execution = (
                _as_mapping(execution_raw, label="change_execution")
                if isinstance(execution_raw, Mapping)
                else {}
            )
            prior: list[Mapping[str, Any]] = []
            if isinstance(prior_path, str) and prior_path.strip():
                raw = _read_path(bag, prior_path, required=False)
                if isinstance(raw, list):
                    prior = [row for row in raw if isinstance(row, Mapping)]
                elif isinstance(raw, Mapping) and isinstance(raw.get("prior_attempts"), list):
                    prior = [row for row in raw["prior_attempts"] if isinstance(row, Mapping)]
            return extract_diagnosis_constraints(
                verification_report=report,
                change_execution=execution,
                prior_attempts=prior,
            )

        if kind == "diagnosis_classify":
            constraints_path = str(reads.get("constraints") or "acc.diagnosis.constraints")
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="diagnosis constraints"
            )
            return classify_failure_evidence(list(constraints.get("evidence") or []))

        if kind == "diagnosis_publish":
            constraints_path = str(reads.get("constraints") or "acc.diagnosis.constraints")
            classification_path = str(reads.get("classification") or "acc.diagnosis.classification")
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="diagnosis constraints"
            )
            classification = _as_mapping(
                _read_path(bag, classification_path),
                label="diagnosis classification",
            )
            return assemble_diagnosis(constraints=constraints, classification=classification)

        if kind == "diagnosis_validate":
            source_path = str(reads.get("source") or "out.diagnosis")
            report = validate_diagnosis(
                _as_mapping(_read_path(bag, source_path), label="diagnosis")
            )
            if parameters.get("fail_if_invalid") and not report["ok"]:
                raise DiscoveryHardNodeError(
                    "diagnosis_validate failed: " + ", ".join(e["path"] for e in report["errors"])
                )
            return report

        raise DiscoveryHardNodeError(f"unsupported diagnosis hard-node kind {kind!r}")


__all__ = [
    "DIAGNOSIS_HARD_KINDS",
    "DiagnosisHardNodeRunner",
]
