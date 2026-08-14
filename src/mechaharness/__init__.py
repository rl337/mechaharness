"""MechaHarness: agentic harness with pluggable inference and harness families."""

from mechaharness.core.contract import RunRequest, RunResponse
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from mechaharness.di import MechaHarnessConfig, SettingsConfig, list_inference_backends
from mechaharness.factory import run
from mechaharness.harness.base import AbstractHarness, HarnessConfig, HarnessResult
from mechaharness.inference.base import InferenceStrategy

__all__ = [
    "AbstractHarness",
    "ChatMessage",
    "CompletionRequest",
    "CompletionResponse",
    "HarnessConfig",
    "HarnessResult",
    "InferenceStrategy",
    "MechaHarnessConfig",
    "Role",
    "RunRequest",
    "RunResponse",
    "SettingsConfig",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
    "list_inference_backends",
    "run",
]

__version__ = "0.1.0"
