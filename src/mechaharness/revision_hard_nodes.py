"""Deterministic StrategyRevision hard-node runners (gastronomic M6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.discovery_hard_nodes import (
    DiscoveryHardNodeError,
    _as_mapping,
    _payload_section,
    _read_path,
)
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.strategy_revision import (
    assemble_strategy_revision,
    decide_revision_gate,
    extract_revision_constraints,
    validate_strategy_revision,
)
from mechaharness.walk_bag import WalkBag, WalkBagPathError, WalkBagSerializeError

REVISION_HARD_KINDS: tuple[str, ...] = (
    "revision_constrain",
    "revision_decide",
    "revision_publish",
    "revision_validate",
)


class RevisionHardNodeRunner(GraphNodeRunner):
    """Run strategy-revision hard-node kinds with atomic bag writes."""

    def __init__(self, kinds: Sequence[str] | None = None) -> None:
        selected = list(kinds) if kinds is not None else list(REVISION_HARD_KINDS)
        unknown = [k for k in selected if k not in REVISION_HARD_KINDS]
        if unknown:
            raise ValueError(f"unknown revision hard-node kinds: {unknown}")
        if not selected:
            raise ValueError("RevisionHardNodeRunner requires at least one kind")
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
        if kind == "revision_constrain":
            diagnosis_path = str(reads.get("diagnosis") or "in.diagnosis")
            plan_path = str(reads.get("change_plan") or "in.change_plan")
            prior_path = reads.get("prior_attempts")
            budget_path = reads.get("retry_budget")
            diagnosis_raw = _read_path(bag, diagnosis_path, required=False)
            plan_raw = _read_path(bag, plan_path, required=False)
            diagnosis = (
                _as_mapping(diagnosis_raw, label="diagnosis")
                if isinstance(diagnosis_raw, Mapping)
                else {}
            )
            plan = (
                _as_mapping(plan_raw, label="change_plan")
                if isinstance(plan_raw, Mapping)
                else {}
            )
            prior: list[Mapping[str, Any]] = []
            if isinstance(prior_path, str) and prior_path.strip():
                raw = _read_path(bag, prior_path, required=False)
                if isinstance(raw, list):
                    prior = [row for row in raw if isinstance(row, Mapping)]
                elif isinstance(raw, Mapping) and isinstance(raw.get("prior_attempts"), list):
                    prior = [row for row in raw["prior_attempts"] if isinstance(row, Mapping)]
            budget: Mapping[str, Any] | None = None
            if isinstance(budget_path, str) and budget_path.strip():
                budget_raw = _read_path(bag, budget_path, required=False)
                if isinstance(budget_raw, Mapping):
                    budget = _as_mapping(budget_raw, label="retry_budget")
            elif isinstance(parameters.get("retry_budget"), Mapping):
                budget = _as_mapping(parameters["retry_budget"], label="retry_budget")
            return extract_revision_constraints(
                diagnosis=diagnosis,
                change_plan=plan,
                prior_attempts=prior,
                retry_budget=budget,
            )

        if kind == "revision_decide":
            constraints_path = str(reads.get("constraints") or "acc.revision.constraints")
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="revision constraints"
            )
            return decide_revision_gate(constraints, parameters=parameters)

        if kind == "revision_publish":
            constraints_path = str(reads.get("constraints") or "acc.revision.constraints")
            decision_path = str(reads.get("decision") or "acc.revision.decision")
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="revision constraints"
            )
            decision = _as_mapping(
                _read_path(bag, decision_path), label="revision decision"
            )
            return assemble_strategy_revision(constraints=constraints, decision=decision)

        if kind == "revision_validate":
            source_path = str(reads.get("source") or "out.strategy_revision")
            report = validate_strategy_revision(
                _as_mapping(_read_path(bag, source_path), label="strategy_revision")
            )
            if parameters.get("fail_if_invalid") and not report["ok"]:
                raise DiscoveryHardNodeError(
                    "revision_validate failed: " + ", ".join(e["path"] for e in report["errors"])
                )
            return report

        raise DiscoveryHardNodeError(f"unsupported revision hard-node kind {kind!r}")


__all__ = [
    "REVISION_HARD_KINDS",
    "RevisionHardNodeRunner",
]
