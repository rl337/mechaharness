"""Compatibility shim — prefer ``mechaharness.isolation.isolation_contract``.

Deprecated public import path. Update call sites to the package when practical.
"""

from mechaharness.isolation.isolation_contract import (
    IsolationContract,
    TemplateIOContract,
)

__all__ = [
    "IsolationContract",
    "TemplateIOContract",
]
