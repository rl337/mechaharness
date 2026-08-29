"""Core package: shared types and exceptions."""

from mechaharness.core.contract import RunRequest, RunResponse
from mechaharness.core.events import (
    AgentRef,
    CoreEvent,
    Event,
    EventLog,
    EventType,
    FanoutEventLog,
    InMemoryEventLog,
    LoggingEventLog,
)
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
    "AgentRef",
    "ChatMessage",
    "CoreEvent",
    "CompletionRequest",
    "CompletionResponse",
    "Event",
    "EventLog",
    "EventType",
    "FanoutEventLog",
    "HarnessError",
    "InMemoryEventLog",
    "InferenceError",
    "LoggingEventLog",
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
