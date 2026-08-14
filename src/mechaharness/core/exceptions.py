"""Package-level exceptions."""

from __future__ import annotations


class MechaHarnessError(Exception):
    """Base error for the library."""


class InferenceError(MechaHarnessError):
    """Raised when an inference backend fails."""


class HarnessError(MechaHarnessError):
    """Raised when a harness run fails."""


class ToolExecutionError(MechaHarnessError):
    """Raised when a registered tool fails during execution."""
