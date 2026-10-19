"""Compatibility shim — prefer ``mechaharness.rule_promotion``.

Deprecated public import path. Update call sites to ``rule_promotion`` when practical.
"""

from mechaharness.rule_promotion import (
    SpecificationDebtLedger,
    SpecificationDebtRecord,
    SpecificationDebtStatus,
    capture_correction,
)

__all__ = [
    "SpecificationDebtStatus",
    "SpecificationDebtRecord",
    "capture_correction",
    "SpecificationDebtLedger",
]
