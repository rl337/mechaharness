"""Compatibility shim — prefer ``mechaharness.decision_log``.

Deprecated public import path. Update call sites to ``decision_log`` when practical.
"""

from mechaharness.decision_log import (
    RecipeAuditRow,
    ReviewAuditRecord,
    summarize_recipe_audit,
)

__all__ = [
    "ReviewAuditRecord",
    "RecipeAuditRow",
    "summarize_recipe_audit",
]
