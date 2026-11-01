"""Deterministic DevelopmentAcceptance hard-node runners (gastronomic M6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.development_acceptance import (
    assemble_development_outcome,
    decide_acceptance_outcome,
    extract_acceptance_constraints,
    validate_development_outcome,
)
from mechaharness.discovery_hard_nodes import (
    DiscoveryHardNodeError,
    _as_mapping,
    _payload_section,
    _read_path,
)
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.walk_bag import WalkBag, WalkBagPathError, WalkBagSerializeError

ACCEPTANCE_HARD_KINDS: tuple[str, ...] = (
    "acceptance_constrain",
    "acceptance_decide",
    "acceptance_publish",
    "acceptance_validate",
)


class AcceptanceHardNodeRunner(GraphNodeRunner):
    """Run development-acceptance hard-node kinds with atomic bag writes."""

    def __init__(self, kinds: Sequence[str] | None = None) -> None:
        selected = list(kinds) if kinds is not None else list(ACCEPTANCE_HARD_KINDS)
        unknown = [k for k in selected if k not in ACCEPTANCE_HARD_KINDS]
        if unknown:
            raise ValueError(f"unknown acceptance hard-node kinds: {unknown}")
        if not selected:
            raise ValueError("AcceptanceHardNodeRunner requires at least one kind")
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
        if kind == "acceptance_constrain":
            contract_path = str(reads.get("change_contract") or "in.change_contract")
            verify_path = str(
                reads.get("verification_report") or "in.verification_report"
            )
            execution_path = str(reads.get("change_execution") or "in.change_execution")
            revision_path = str(
                reads.get("strategy_revision") or "in.strategy_revision"
            )
            coverage_path = reads.get("coverage")
            judge_path = reads.get("judge_opinion")

            def _optional_map(path: str, label: str) -> dict[str, Any]:
                raw = _read_path(bag, path, required=False)
                if isinstance(raw, Mapping):
                    return dict(_as_mapping(raw, label=label))
                return {}

            coverage: Mapping[str, Any] | None = None
            if isinstance(coverage_path, str) and coverage_path.strip():
                coverage = _optional_map(coverage_path, "coverage") or None
            elif isinstance(parameters.get("coverage"), Mapping):
                coverage = _as_mapping(parameters["coverage"], label="coverage")

            judge: Mapping[str, Any] | None = None
            if isinstance(judge_path, str) and judge_path.strip():
                judge = _optional_map(judge_path, "judge_opinion") or None
            elif isinstance(parameters.get("judge_opinion"), Mapping):
                judge = _as_mapping(parameters["judge_opinion"], label="judge_opinion")

            return extract_acceptance_constraints(
                change_contract=_optional_map(contract_path, "change_contract"),
                verification_report=_optional_map(verify_path, "verification_report"),
                change_execution=_optional_map(execution_path, "change_execution"),
                strategy_revision=_optional_map(revision_path, "strategy_revision"),
                coverage=coverage,
                judge_opinion=judge,
            )

        if kind == "acceptance_decide":
            constraints_path = str(
                reads.get("constraints") or "acc.acceptance.constraints"
            )
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="acceptance constraints"
            )
            return decide_acceptance_outcome(constraints, parameters=parameters)

        if kind == "acceptance_publish":
            constraints_path = str(
                reads.get("constraints") or "acc.acceptance.constraints"
            )
            decision_path = str(reads.get("decision") or "acc.acceptance.decision")
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="acceptance constraints"
            )
            decision = _as_mapping(
                _read_path(bag, decision_path), label="acceptance decision"
            )
            return assemble_development_outcome(
                constraints=constraints, decision=decision
            )

        if kind == "acceptance_validate":
            source_path = str(reads.get("source") or "out.development_outcome")
            report = validate_development_outcome(
                _as_mapping(_read_path(bag, source_path), label="development_outcome")
            )
            if parameters.get("fail_if_invalid") and not report["ok"]:
                raise DiscoveryHardNodeError(
                    "acceptance_validate failed: "
                    + ", ".join(e["path"] for e in report["errors"])
                )
            return report

        raise DiscoveryHardNodeError(f"unsupported acceptance hard-node kind {kind!r}")


__all__ = [
    "ACCEPTANCE_HARD_KINDS",
    "AcceptanceHardNodeRunner",
]
