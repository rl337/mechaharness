"""Compatibility shim — prefer ``mechaharness.operation_registry``.

Tool phases (MH-DOTS-03) live beside ``OperationContract``. Deprecated import path.
"""

from mechaharness.operation_registry import ToolPhase, assert_tool_phase_allows_effects

__all__ = ["ToolPhase", "assert_tool_phase_allows_effects"]
