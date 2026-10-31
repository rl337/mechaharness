"""Deterministic VerificationReport hard-node runners (gastronomic M6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mechaharness.change_verification import (
    assemble_verification_report,
    check_immutable_invariants,
    extract_verification_constraints,
    run_host_verify_runs,
    validate_verification_report,
)
from mechaharness.discovery_hard_nodes import (
    DiscoveryHardNodeError,
    _as_mapping,
    _payload_section,
    _read_path,
    _resolve_workspace_root,
)
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.walk_bag import WalkBag, WalkBagPathError, WalkBagSerializeError

VERIFICATION_HARD_KINDS: tuple[str, ...] = (
    "verification_constrain",
    "verification_run",
    "verification_publish",
    "verification_validate",
)


class VerificationHardNodeRunner(GraphNodeRunner):
    """Run change-verification hard-node kinds with atomic bag writes."""

    def __init__(
        self,
        kinds: Sequence[str] | None = None,
        *,
        default_workspace: Path | str | None = None,
    ) -> None:
        selected = list(kinds) if kinds is not None else list(VERIFICATION_HARD_KINDS)
        unknown = [k for k in selected if k not in VERIFICATION_HARD_KINDS]
        if unknown:
            raise ValueError(f"unknown verification hard-node kinds: {unknown}")
        if not selected:
            raise ValueError("VerificationHardNodeRunner requires at least one kind")
        self._kinds = selected
        self._default_workspace = (
            Path(default_workspace).expanduser().resolve()
            if default_workspace is not None
            else None
        )

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
        if kind == "verification_constrain":
            contract_path = str(reads.get("contract") or "in.change_contract")
            execution_path = str(reads.get("execution") or "in.change_execution")
            extras_path = reads.get("verify_runs")
            contract_raw = _read_path(bag, contract_path, required=False)
            execution_raw = _read_path(bag, execution_path, required=False)
            contract = (
                _as_mapping(contract_raw, label="change_contract")
                if isinstance(contract_raw, Mapping)
                else {}
            )
            execution = (
                _as_mapping(execution_raw, label="change_execution")
                if isinstance(execution_raw, Mapping)
                else {}
            )
            extras: list[Mapping[str, Any]] = []
            if isinstance(extras_path, str) and extras_path.strip():
                raw = _read_path(bag, extras_path, required=False)
                if isinstance(raw, list):
                    extras = [row for row in raw if isinstance(row, Mapping)]
                elif isinstance(raw, Mapping) and isinstance(raw.get("verify_runs"), list):
                    extras = [row for row in raw["verify_runs"] if isinstance(row, Mapping)]
            elif isinstance(parameters.get("verify_runs"), list):
                extras = [row for row in parameters["verify_runs"] if isinstance(row, Mapping)]
            return extract_verification_constraints(
                change_contract=contract,
                change_execution=execution,
                verify_runs=extras,
            )

        if kind == "verification_run":
            constraints_path = str(reads.get("constraints") or "acc.verification.constraints")
            workspace_path = str(reads.get("workspace") or "in.workspace")
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="verification constraints"
            )
            workspace_value = _read_path(bag, workspace_path, required=False)
            root = _resolve_workspace_root(
                workspace_value,
                default_workspace=self._default_workspace,
            )
            run_results = run_host_verify_runs(
                root=root,
                specs=list(constraints.get("verify_runs") or []),
            )
            invariant_report = check_immutable_invariants(
                root=root,
                invariants=list(constraints.get("immutable_invariants") or []),
            )
            return {
                "run_results": run_results,
                "invariant_report": invariant_report,
            }

        if kind == "verification_publish":
            constraints_path = str(reads.get("constraints") or "acc.verification.constraints")
            receipt_path = str(reads.get("receipt") or "acc.verification.run_receipt")
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="verification constraints"
            )
            receipt = _as_mapping(_read_path(bag, receipt_path), label="verification run receipt")
            return assemble_verification_report(
                constraints=constraints,
                run_results=list(receipt.get("run_results") or []),
                invariant_report=(
                    receipt.get("invariant_report")
                    if isinstance(receipt.get("invariant_report"), Mapping)
                    else None
                ),
            )

        if kind == "verification_validate":
            source_path = str(reads.get("source") or "out.verification_report")
            report = validate_verification_report(
                _as_mapping(_read_path(bag, source_path), label="verification_report")
            )
            if parameters.get("fail_if_invalid") and not report["ok"]:
                raise DiscoveryHardNodeError(
                    "verification_validate failed: "
                    + ", ".join(e["path"] for e in report["errors"])
                )
            return report

        raise DiscoveryHardNodeError(f"unsupported verification hard-node kind {kind!r}")


__all__ = [
    "VERIFICATION_HARD_KINDS",
    "VerificationHardNodeRunner",
]
