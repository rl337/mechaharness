"""Deterministic ChangeExecution hard-node runners (gastronomic M6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pyiv.files import Filesystem, RealFilesystem

from mechaharness.change_execution import (
    apply_file_revisions,
    assemble_change_execution,
    extract_execution_constraints,
    validate_change_execution,
)
from mechaharness.core.access import FsWrite
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

EXECUTION_HARD_KINDS: tuple[str, ...] = (
    "execution_constrain",
    "execution_apply",
    "execution_publish",
    "execution_validate",
)


class ExecutionHardNodeRunner(GraphNodeRunner):
    """Run change-execution hard-node kinds with atomic bag writes."""

    def __init__(
        self,
        kinds: Sequence[str] | None = None,
        *,
        filesystem: Filesystem | None = None,
        default_workspace: Path | str | None = None,
    ) -> None:
        selected = list(kinds) if kinds is not None else list(EXECUTION_HARD_KINDS)
        unknown = [k for k in selected if k not in EXECUTION_HARD_KINDS]
        if unknown:
            raise ValueError(f"unknown execution hard-node kinds: {unknown}")
        if not selected:
            raise ValueError("ExecutionHardNodeRunner requires at least one kind")
        self._kinds = selected
        self._fs = filesystem if filesystem is not None else RealFilesystem()
        self._default_workspace = (
            Path(default_workspace).expanduser().resolve()
            if default_workspace is not None
            else None
        )

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        if "execution_apply" in self._kinds:
            return [FsWrite]
        return []

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
        if kind == "execution_constrain":
            slice_path = reads.get("approved_slice")
            plan_path = reads.get("change_plan")
            approved = None
            if isinstance(slice_path, str) and slice_path.strip():
                raw = _read_path(bag, slice_path, required=False)
                if isinstance(raw, Mapping):
                    approved = raw
            plan = None
            if isinstance(plan_path, str) and plan_path.strip():
                raw_p = _read_path(bag, plan_path, required=False)
                if isinstance(raw_p, Mapping):
                    plan = raw_p
            return extract_execution_constraints(
                approved_slice=approved,
                change_plan=plan,
            )

        if kind == "execution_apply":
            constraints_path = str(
                reads.get("constraints") or "acc.execution.constraints"
            )
            revisions_path = str(reads.get("revisions") or "in.file_revisions")
            workspace_path = str(reads.get("workspace") or "in.workspace")
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="execution constraints"
            )
            if str(constraints.get("status") or "") != "ok":
                raise DiscoveryHardNodeError(
                    "execution_apply requires ok constraints "
                    f"(got {constraints.get('status')!r})"
                )
            revisions_raw = _read_path(bag, revisions_path, required=False)
            if isinstance(revisions_raw, Mapping) and "revisions" in revisions_raw:
                revisions = list(revisions_raw.get("revisions") or [])
            elif isinstance(revisions_raw, list):
                revisions = revisions_raw
            else:
                revisions = list(parameters.get("revisions") or [])
            workspace_value = _read_path(bag, workspace_path, required=False)
            root = _resolve_workspace_root(
                workspace_value,
                default_workspace=self._default_workspace,
            )
            return apply_file_revisions(
                fs=self._fs,
                root=root,
                revisions=revisions,
                allowed_paths=list(constraints.get("allowed_paths") or []),
            )

        if kind == "execution_publish":
            constraints_path = str(
                reads.get("constraints") or "acc.execution.constraints"
            )
            receipt_path = str(reads.get("receipt") or "acc.execution.apply_receipt")
            constraints = _as_mapping(
                _read_path(bag, constraints_path), label="execution constraints"
            )
            receipt = _as_mapping(
                _read_path(bag, receipt_path), label="apply receipt"
            )
            return assemble_change_execution(
                constraints=constraints,
                apply_receipt=receipt,
            )

        if kind == "execution_validate":
            source_path = str(reads.get("source") or "out.change_execution")
            report = validate_change_execution(
                _as_mapping(_read_path(bag, source_path), label="change_execution")
            )
            if parameters.get("fail_if_invalid") and not report["ok"]:
                raise DiscoveryHardNodeError(
                    "execution_validate failed: "
                    + ", ".join(e["path"] for e in report["errors"])
                )
            return report

        raise DiscoveryHardNodeError(f"unsupported execution hard-node kind {kind!r}")


__all__ = [
    "EXECUTION_HARD_KINDS",
    "ExecutionHardNodeRunner",
]
