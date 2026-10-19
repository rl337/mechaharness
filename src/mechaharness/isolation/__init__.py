"""Isolation seams: IO/isolation contracts, workspace providers, cross-task guard.

Canonical home for the isolation leaves; the old top-level modules
(``mechaharness.isolation_contract`` etc.) are thin re-export shims.
"""

from __future__ import annotations

from mechaharness.isolation.cross_task_isolation import (
    CrossTaskIsolationGuard,
    IsolationViolation,
)
from mechaharness.isolation.isolation_contract import (
    IsolationContract,
    TemplateIOContract,
)
from mechaharness.isolation.workspace_isolation import (
    InMemoryWorkspaceIsolationProvider,
    WorkspaceIsolationHandle,
    WorkspaceIsolationProvider,
    WorkspaceIsolationRequest,
)

__all__ = [
    "IsolationContract",
    "TemplateIOContract",
    "WorkspaceIsolationRequest",
    "WorkspaceIsolationHandle",
    "WorkspaceIsolationProvider",
    "InMemoryWorkspaceIsolationProvider",
    "IsolationViolation",
    "CrossTaskIsolationGuard",
]
