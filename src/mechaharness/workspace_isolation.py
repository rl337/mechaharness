"""Compatibility shim — prefer ``mechaharness.isolation.workspace_isolation``.

Deprecated public import path. Update call sites to the package when practical.
"""

from mechaharness.isolation.workspace_isolation import (
    InMemoryWorkspaceIsolationProvider,
    WorkspaceIsolationHandle,
    WorkspaceIsolationProvider,
    WorkspaceIsolationRequest,
)

__all__ = [
    "WorkspaceIsolationRequest",
    "WorkspaceIsolationHandle",
    "WorkspaceIsolationProvider",
    "InMemoryWorkspaceIsolationProvider",
]
