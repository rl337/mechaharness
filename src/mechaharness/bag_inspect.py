"""Snapshot-bound bag / prior-response inspection (gastronomic M3).

Inference tools read an **immutable** bag snapshot captured at invocation
start — never the live bag — and authorized prior response records.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.types import ToolDefinition
from mechaharness.walk_bag import WalkBag, WalkBagPathError

InspectStatus = Literal[
    "ok",
    "denied",
    "not_found",
    "truncated",
    "unavailable",
    "budget_exhausted",
]


class PriorResponseRecord(BaseModel):
    """Immutable prior inference publication available for inspection."""

    model_config = ConfigDict(extra="allow")

    invocation_id: str
    snapshot_id: str | None = None
    node_id: str | None = None
    content: str | None = None
    published: Any = None
    bag_write: str | None = None


class InspectionOutcome(BaseModel):
    """Structured tool result for snapshot inspection."""

    model_config = ConfigDict(extra="forbid")

    status: InspectStatus
    tool: str
    path: str | None = None
    invocation_id: str | None = None
    field: str | None = None
    value: Any = None
    truncated: bool = False
    reason: str | None = None
    snapshot_id: str | None = None
    bytes: int = 0


class InspectionPolicy(BaseModel):
    """Declared authorization and budgets for one inference invocation."""

    model_config = ConfigDict(extra="forbid")

    allowed_paths: list[str] = Field(default_factory=list)
    allowed_invocation_ids: list[str] | None = None
    max_tool_calls: int = 8
    max_bytes: int = 2048
    default_limit: int = 512


class SnapshotInspectionToolkit:
    """Read-only inspectors bound to one frozen bag snapshot + prior records."""

    INSPECT_BAG = "inspect_bag"
    INSPECT_PRIOR = "inspect_prior_response"

    def __init__(
        self,
        snapshot: WalkBag,
        *,
        snapshot_id: str,
        policy: InspectionPolicy,
        prior_responses: Mapping[str, PriorResponseRecord] | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._snapshot_id = snapshot_id
        self._policy = policy
        self._allowed = {str(p) for p in policy.allowed_paths}
        self._priors = {str(k): v for k, v in (prior_responses or {}).items()}
        self._calls = 0
        self._bytes_spent = 0
        self.transcript: list[dict[str, Any]] = []

    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=self.INSPECT_BAG,
                description=(
                    "Read a declared bag path from the immutable invocation "
                    "snapshot. Never observes later live-bag mutations."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "offset": {"type": "integer", "minimum": 0},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path"],
                },
            ),
            ToolDefinition(
                name=self.INSPECT_PRIOR,
                description=(
                    "Read a field from an authorized prior inference response "
                    "record (immutable)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "invocation_id": {"type": "string"},
                        "field": {
                            "type": "string",
                            "enum": ["content", "published", "bag_write", "snapshot_id"],
                        },
                    },
                    "required": ["invocation_id", "field"],
                },
            ),
        ]

    def inspect_bag(
        self,
        path: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> InspectionOutcome:
        self._calls += 1
        if self._calls > self._policy.max_tool_calls:
            return self._record(
                InspectionOutcome(
                    status="budget_exhausted",
                    tool=self.INSPECT_BAG,
                    path=path,
                    reason="max_tool_calls",
                    snapshot_id=self._snapshot_id,
                )
            )
        if path not in self._allowed:
            return self._record(
                InspectionOutcome(
                    status="denied",
                    tool=self.INSPECT_BAG,
                    path=path,
                    reason="path_not_allowed",
                    snapshot_id=self._snapshot_id,
                )
            )
        try:
            value = self._snapshot.path_get(path)
        except WalkBagPathError:
            return self._record(
                InspectionOutcome(
                    status="not_found",
                    tool=self.INSPECT_BAG,
                    path=path,
                    reason="missing_path",
                    snapshot_id=self._snapshot_id,
                )
            )
        rendered, truncated, nbytes = self._render(
            value, offset=offset, limit=limit or self._policy.default_limit
        )
        if self._bytes_spent + nbytes > self._policy.max_bytes and nbytes:
            # Still return truncated fragment within remaining budget.
            remain = max(0, self._policy.max_bytes - self._bytes_spent)
            if remain <= 0:
                return self._record(
                    InspectionOutcome(
                        status="budget_exhausted",
                        tool=self.INSPECT_BAG,
                        path=path,
                        reason="max_bytes",
                        snapshot_id=self._snapshot_id,
                    )
                )
            rendered, truncated, nbytes = self._render(value, offset=offset, limit=remain)
        self._bytes_spent += nbytes
        return self._record(
            InspectionOutcome(
                status="truncated" if truncated else "ok",
                tool=self.INSPECT_BAG,
                path=path,
                value=rendered,
                truncated=truncated,
                snapshot_id=self._snapshot_id,
                bytes=nbytes,
            )
        )

    def inspect_prior_response(
        self,
        invocation_id: str,
        field: str,
    ) -> InspectionOutcome:
        self._calls += 1
        if self._calls > self._policy.max_tool_calls:
            return self._record(
                InspectionOutcome(
                    status="budget_exhausted",
                    tool=self.INSPECT_PRIOR,
                    invocation_id=invocation_id,
                    field=field,
                    reason="max_tool_calls",
                    snapshot_id=self._snapshot_id,
                )
            )
        resolved_id = invocation_id
        if resolved_id in {"", "*"}:
            # Story/host convenience: latest recorded prior response.
            if not self._priors:
                return self._record(
                    InspectionOutcome(
                        status="not_found",
                        tool=self.INSPECT_PRIOR,
                        invocation_id=invocation_id,
                        field=field,
                        reason="unknown_invocation",
                        snapshot_id=self._snapshot_id,
                    )
                )
            resolved_id = next(reversed(self._priors))
        allowed_ids = self._policy.allowed_invocation_ids
        if allowed_ids is not None and resolved_id not in allowed_ids:
            return self._record(
                InspectionOutcome(
                    status="denied",
                    tool=self.INSPECT_PRIOR,
                    invocation_id=resolved_id,
                    field=field,
                    reason="invocation_not_allowed",
                    snapshot_id=self._snapshot_id,
                )
            )
        record = self._priors.get(resolved_id)
        if record is None:
            return self._record(
                InspectionOutcome(
                    status="not_found",
                    tool=self.INSPECT_PRIOR,
                    invocation_id=resolved_id,
                    field=field,
                    reason="unknown_invocation",
                    snapshot_id=self._snapshot_id,
                )
            )
        if field not in {"content", "published", "bag_write", "snapshot_id"}:
            return self._record(
                InspectionOutcome(
                    status="denied",
                    tool=self.INSPECT_PRIOR,
                    invocation_id=resolved_id,
                    field=field,
                    reason="field_not_allowed",
                    snapshot_id=self._snapshot_id,
                )
            )
        value = getattr(record, field)
        rendered, truncated, nbytes = self._render(
            value, offset=0, limit=self._policy.default_limit
        )
        self._bytes_spent += nbytes
        return self._record(
            InspectionOutcome(
                status="truncated" if truncated else "ok",
                tool=self.INSPECT_PRIOR,
                invocation_id=resolved_id,
                field=field,
                value=rendered,
                truncated=truncated,
                snapshot_id=record.snapshot_id or self._snapshot_id,
                bytes=nbytes,
            )
        )

    def dispatch(self, name: str, arguments: Mapping[str, Any]) -> InspectionOutcome:
        if name == self.INSPECT_BAG:
            return self.inspect_bag(
                str(arguments.get("path") or ""),
                offset=int(arguments.get("offset") or 0),
                limit=(
                    int(arguments["limit"])
                    if arguments.get("limit") is not None
                    else None
                ),
            )
        if name == self.INSPECT_PRIOR:
            return self.inspect_prior_response(
                str(arguments.get("invocation_id") or ""),
                str(arguments.get("field") or "content"),
            )
        return self._record(
            InspectionOutcome(
                status="unavailable",
                tool=name,
                reason="unknown_tool",
                snapshot_id=self._snapshot_id,
            )
        )

    def _record(self, outcome: InspectionOutcome) -> InspectionOutcome:
        self.transcript.append(outcome.model_dump(mode="json"))
        return outcome

    @staticmethod
    def _render(
        value: Any, *, offset: int, limit: int
    ) -> tuple[Any, bool, int]:
        if isinstance(value, str):
            chunk = value[offset : offset + limit]
            truncated = (offset + limit) < len(value)
            return chunk, truncated, len(chunk.encode("utf-8"))
        text = json.dumps(value, sort_keys=True, default=str)
        raw = text.encode("utf-8")
        if offset:
            raw = raw[offset:]
        truncated = len(raw) > limit
        piece = raw[:limit]
        try:
            decoded: Any = json.loads(piece.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            decoded = piece.decode("utf-8", errors="replace")
        return decoded, truncated, len(piece)


def new_invocation_id() -> str:
    return str(uuid4())


def inspection_policy_from_mapping(raw: Mapping[str, Any] | InspectionPolicy) -> InspectionPolicy:
    if isinstance(raw, InspectionPolicy):
        return raw
    return InspectionPolicy.model_validate(raw)


__all__ = [
    "InspectionOutcome",
    "InspectionPolicy",
    "PriorResponseRecord",
    "SnapshotInspectionToolkit",
    "inspection_policy_from_mapping",
    "new_invocation_id",
]
