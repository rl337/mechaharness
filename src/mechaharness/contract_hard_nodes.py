"""Deterministic ChangeContract hard-node runners (gastronomic M6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.change_contract import (
    assemble_change_contract,
    freeze_prior_invariants,
    validate_change_contract,
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

CONTRACT_HARD_KINDS: tuple[str, ...] = (
    "invariant_freeze",
    "contract_assemble",
    "contract_validate",
)


class ContractHardNodeRunner(GraphNodeRunner):
    """Run contract-extraction hard-node kinds with atomic bag writes."""

    def __init__(self, kinds: Sequence[str] | None = None) -> None:
        selected = list(kinds) if kinds is not None else list(CONTRACT_HARD_KINDS)
        unknown = [k for k in selected if k not in CONTRACT_HARD_KINDS]
        if unknown:
            raise ValueError(f"unknown contract hard-node kinds: {unknown}")
        if not selected:
            raise ValueError("ContractHardNodeRunner requires at least one kind")
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
        if kind == "invariant_freeze":
            inventory_path = str(reads.get("inventory") or "acc.stages.discovery")
            goal_path = str(reads.get("goal") or "in.goal")
            inventory = _as_mapping(
                _read_path(bag, inventory_path), label="inventory"
            )
            goal = _read_path(bag, goal_path, required=False)
            return {
                "invariants": freeze_prior_invariants(
                    inventory,
                    goal=goal if isinstance(goal, str) else str(goal or ""),
                )
            }

        if kind == "contract_assemble":
            inventory_path = str(reads.get("inventory") or "acc.stages.discovery")
            goal_path = str(reads.get("goal") or "in.goal")
            proposed_path = reads.get("proposed")
            frozen_path = reads.get("frozen")
            inventory = _as_mapping(
                _read_path(bag, inventory_path), label="inventory"
            )
            goal = _read_path(bag, goal_path)
            proposed = None
            if isinstance(proposed_path, str) and proposed_path.strip():
                raw = _read_path(bag, proposed_path, required=False)
                if isinstance(raw, Mapping):
                    proposed = raw
            frozen = None
            if isinstance(frozen_path, str) and frozen_path.strip():
                frozen_raw = _read_path(bag, frozen_path, required=False)
                if isinstance(frozen_raw, Mapping):
                    frozen = list(frozen_raw.get("invariants") or [])
                elif isinstance(frozen_raw, list):
                    frozen = frozen_raw
            return assemble_change_contract(
                goal=goal,
                inventory=inventory,
                proposed=proposed,
                frozen_invariants=frozen,
            )

        if kind == "contract_validate":
            source_path = str(reads.get("source") or "out.change_contract")
            report = validate_change_contract(
                _as_mapping(_read_path(bag, source_path), label="change_contract")
            )
            if parameters.get("fail_if_invalid") and not report["ok"]:
                raise DiscoveryHardNodeError(
                    "contract_validate failed: "
                    + ", ".join(e["path"] for e in report["errors"])
                )
            return report

        raise DiscoveryHardNodeError(f"unsupported contract hard-node kind {kind!r}")


__all__ = [
    "CONTRACT_HARD_KINDS",
    "ContractHardNodeRunner",
]
