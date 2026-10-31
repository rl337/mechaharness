"""Deterministic ChangePlan hard-node runners (gastronomic M6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.change_plan import (
    assemble_change_plan,
    extract_plan_constraints,
    validate_change_plan,
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

PLAN_HARD_KINDS: tuple[str, ...] = (
    "plan_constrain",
    "plan_assemble",
    "plan_validate",
)


class PlanHardNodeRunner(GraphNodeRunner):
    """Run change-decomposition hard-node kinds with atomic bag writes."""

    def __init__(self, kinds: Sequence[str] | None = None) -> None:
        selected = list(kinds) if kinds is not None else list(PLAN_HARD_KINDS)
        unknown = [k for k in selected if k not in PLAN_HARD_KINDS]
        if unknown:
            raise ValueError(f"unknown plan hard-node kinds: {unknown}")
        if not selected:
            raise ValueError("PlanHardNodeRunner requires at least one kind")
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
        if kind == "plan_constrain":
            contract_path = str(reads.get("contract") or "in.change_contract")
            contract = _as_mapping(_read_path(bag, contract_path), label="change_contract")
            return extract_plan_constraints(contract)

        if kind == "plan_assemble":
            contract_path = str(reads.get("contract") or "in.change_contract")
            proposed_path = reads.get("proposed")
            constraints_path = reads.get("constraints")
            inventory_path = reads.get("inventory")
            contract = _as_mapping(_read_path(bag, contract_path), label="change_contract")
            proposed = None
            if isinstance(proposed_path, str) and proposed_path.strip():
                raw = _read_path(bag, proposed_path, required=False)
                if isinstance(raw, Mapping):
                    proposed = raw
            constraints = None
            if isinstance(constraints_path, str) and constraints_path.strip():
                raw_c = _read_path(bag, constraints_path, required=False)
                if isinstance(raw_c, Mapping):
                    constraints = raw_c
            inventory = None
            if isinstance(inventory_path, str) and inventory_path.strip():
                raw_i = _read_path(bag, inventory_path, required=False)
                if isinstance(raw_i, Mapping):
                    inventory = raw_i
            return assemble_change_plan(
                contract=contract,
                proposed=proposed,
                constraints=constraints,
                inventory=inventory,
            )

        if kind == "plan_validate":
            source_path = str(reads.get("source") or "out.change_plan")
            report = validate_change_plan(
                _as_mapping(_read_path(bag, source_path), label="change_plan")
            )
            if parameters.get("fail_if_invalid") and not report["ok"]:
                raise DiscoveryHardNodeError(
                    "plan_validate failed: "
                    + ", ".join(e["path"] for e in report["errors"])
                )
            return report

        raise DiscoveryHardNodeError(f"unsupported plan hard-node kind {kind!r}")


__all__ = [
    "PLAN_HARD_KINDS",
    "PlanHardNodeRunner",
]
