"""Shared domain types used across inference and harness layers.

These models form the stable public contract. Keep them serializable so
future language bindings (via FFI / IPC / OpenAPI) can share the same shapes.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolDefinition(BaseModel):
    """Provider-agnostic tool/function schema exposed to a harness."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """Model-requested tool invocation (id, name, decoded arguments)."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Result of executing a tool, fed back as a tool-role message."""

    tool_call_id: str
    content: str
    is_error: bool = False


class ChatMessage(BaseModel):
    """One turn in a chat transcript (portable across providers)."""

    role: Role
    content: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    reasoning_content: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class CompletionRequest(BaseModel):
    """Normalized request handed to an InferenceStrategy."""

    model: str
    messages: list[ChatMessage]
    tools: list[ToolDefinition] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stop: list[str] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    """Token usage reported by a provider (fields may be unset)."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class CompletionResponse(BaseModel):
    """Normalized response returned by an InferenceStrategy."""

    message: ChatMessage
    finish_reason: str | None = None
    usage: Usage | None = None
    raw: dict[str, Any] | None = None
    # Nested Completer rollup: ``mechaharness.core.access.CostReport`` when set.
    cost: Any | None = None
