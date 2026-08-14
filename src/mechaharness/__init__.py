"""MechaHarness: agentic harness with pluggable inference and harness families."""

from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from mechaharness.harness.base import AbstractHarness, HarnessConfig, HarnessResult
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.registry import create_inference, list_inference_backends

__all__ = [
    "AbstractHarness",
    "ChatMessage",
    "CompletionRequest",
    "CompletionResponse",
    "HarnessConfig",
    "HarnessResult",
    "InferenceStrategy",
    "Role",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
    "create_inference",
    "list_inference_backends",
]

__version__ = "0.1.0"
