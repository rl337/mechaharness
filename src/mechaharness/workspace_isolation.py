"""Host-provided workspace / sandbox isolation capability seam.

WalkingLabs L13 and Codex treat workspace isolation as a capability, not a
prompt instruction
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-13-loop-engineering/,
https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/codex/).

MechaHarness defines the provider protocol; worktrees/containers/remotes stay
host implementations::

    >>> from mechaharness.workspace_isolation import (
    ...     InMemoryWorkspaceIsolationProvider, WorkspaceIsolationRequest,
    ... )
    >>> provider = InMemoryWorkspaceIsolationProvider()
    >>> handle = provider.acquire(WorkspaceIsolationRequest(label="branch-a"))
    >>> handle.provider_kind
    'memory'
    >>> provider.release(handle)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceIsolationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    label: str = "default"
    write_scopes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceIsolationHandle(BaseModel):
    model_config = ConfigDict(extra="allow")

    handle_id: str = Field(default_factory=lambda: str(uuid4()))
    label: str
    provider_kind: str
    root_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceIsolationProvider(ABC):
    """Host seam: acquire/release isolated workspaces without leaking mechanism."""

    @abstractmethod
    def acquire(self, request: WorkspaceIsolationRequest) -> WorkspaceIsolationHandle:
        raise NotImplementedError

    @abstractmethod
    def release(self, handle: WorkspaceIsolationHandle) -> None:
        raise NotImplementedError


class InMemoryWorkspaceIsolationProvider(WorkspaceIsolationProvider):
    """Test/default provider that tracks handles without real isolation."""

    def __init__(self) -> None:
        self._active: dict[str, WorkspaceIsolationHandle] = {}

    def acquire(self, request: WorkspaceIsolationRequest) -> WorkspaceIsolationHandle:
        handle = WorkspaceIsolationHandle(
            label=request.label,
            provider_kind="memory",
            root_ref=f"memory:{request.label}",
            metadata=dict(request.metadata),
        )
        self._active[handle.handle_id] = handle
        return handle

    def release(self, handle: WorkspaceIsolationHandle) -> None:
        self._active.pop(handle.handle_id, None)
