"""OpenAI Chat Completions wire models (HTTP JSON only).

Domain types live in ``mechaharness.core.types``. This module describes the
provider payload so ``OpenAICompatStrategy`` can ``model_validate`` /
``model_dump`` instead of nested ``dict.get`` chains.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpenAIWireModel(BaseModel):
    """Base for OpenAI-shaped JSON; unknown fields are kept for forward-compat."""

    model_config = ConfigDict(extra="allow")


class OpenAIFunction(OpenAIWireModel):
    name: str = ""
    arguments: str | dict[str, Any] = "{}"


class OpenAIToolCall(OpenAIWireModel):
    id: str = ""
    type: str = "function"
    function: OpenAIFunction = Field(default_factory=OpenAIFunction)


class OpenAIFunctionDef(OpenAIWireModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class OpenAIToolDef(OpenAIWireModel):
    type: str = "function"
    function: OpenAIFunctionDef


class OpenAIChatMessage(OpenAIWireModel):
    role: str
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[OpenAIToolCall] | None = None
    reasoning_content: str | None = None
    reasoning: str | dict[str, Any] | None = None

    @property
    def resolved_reasoning_content(self) -> str | None:
        """Prefer ``reasoning_content``, else coerce ``reasoning`` string/object."""
        if self.reasoning_content:
            return self.reasoning_content
        if self.reasoning is None:
            return None
        if isinstance(self.reasoning, str):
            return self.reasoning or None
        content = self.reasoning.get("content")
        if content:
            return str(content)
        text = self.reasoning.get("text")
        if text:
            return str(text)
        return str(self.reasoning) if self.reasoning else None


class OpenAIChatCompletionRequest(OpenAIWireModel):
    model: str
    messages: list[OpenAIChatMessage]
    tools: list[OpenAIToolDef] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stop: list[str] | None = None
    stream: bool | None = None


class OpenAIUsage(OpenAIWireModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class OpenAIResponseMessage(OpenAIChatMessage):
    """Assistant (or tool) message on a completion choice."""


class OpenAIChoice(OpenAIWireModel):
    index: int = 0
    message: OpenAIResponseMessage
    finish_reason: str | None = None


class OpenAIChatCompletionResponse(OpenAIWireModel):
    id: str | None = None
    object: str | None = None
    created: int | None = None
    model: str | None = None
    choices: list[OpenAIChoice] = Field(default_factory=list)
    usage: OpenAIUsage | None = None


class OpenAIDelta(OpenAIWireModel):
    role: str | None = None
    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[OpenAIToolCall] | None = None


class OpenAIStreamChoice(OpenAIWireModel):
    index: int = 0
    delta: OpenAIDelta = Field(default_factory=OpenAIDelta)
    finish_reason: str | None = None


class OpenAIChatCompletionChunk(OpenAIWireModel):
    id: str | None = None
    object: str | None = None
    created: int | None = None
    model: str | None = None
    choices: list[OpenAIStreamChoice] = Field(default_factory=list)
    usage: OpenAIUsage | None = None


def decode_tool_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """Decode OpenAI tool ``function.arguments`` (often a JSON string) to a dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}
