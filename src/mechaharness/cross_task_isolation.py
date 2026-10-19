"""Compatibility shim — prefer ``mechaharness.isolation.cross_task_isolation``.

Deprecated public import path. Update call sites to the package when practical.
"""

from mechaharness.isolation.cross_task_isolation import (
    CrossTaskIsolationGuard,
    IsolationViolation,
)

__all__ = [
    "IsolationViolation",
    "CrossTaskIsolationGuard",
]
