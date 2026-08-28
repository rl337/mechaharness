"""Core package: shared types and exceptions."""

from mechaharness.core.contract import RunRequest, RunResponse
from mechaharness.core.exceptions import (
    HarnessError,
    InferenceError,
    MechaHarnessError,
    ToolExecutionError,
)
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)

__all__ = [
    "ChatMessage",
    "CompletionRequest",
    "CompletionResponse",
    "HarnessError",
    "InferenceError",
    "MechaHarnessError",
    "Role",
    "RunRequest",
    "RunResponse",
    "ToolCall",
    "ToolDefinition",
    "ToolExecutionError",
    "ToolResult",
    "Usage",
]
