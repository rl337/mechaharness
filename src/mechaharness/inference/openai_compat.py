"""OpenAI-compatible inference strategy.

Covers OpenAI, Azure OpenAI (compat endpoints), Groq, Together, Fireworks,
LM Studio, vLLM, Ollama (OpenAI mode), and most local OpenAI-shaped servers.

HTTP JSON is modeled in ``mechaharness.inference.openai_wire``. Portable domain
types stay in ``mechaharness.core.types``; this strategy maps between them.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from mechaharness.config import Settings
from mechaharness.core.exceptions import InferenceError
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    ToolCall,
    ToolDefinition,
    Usage,
)
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.openai_wire import (
    OpenAIChatCompletionChunk,
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIChatMessage,
    OpenAIFunction,
    OpenAIFunctionDef,
    OpenAIResponseMessage,
    OpenAIToolCall,
    OpenAIToolDef,
    OpenAIUsage,
    decode_tool_arguments,
)


def _domain_tool_calls_to_wire(calls: list[ToolCall] | None) -> list[OpenAIToolCall] | None:
    if not calls:
        return None
    return [
        OpenAIToolCall(
            id=tc.id,
            type="function",
            function=OpenAIFunction(
                name=tc.name,
                arguments=json.dumps(tc.arguments),
            ),
        )
        for tc in calls
    ]


def _domain_messages_to_wire(messages: list[ChatMessage]) -> list[OpenAIChatMessage]:
    wire: list[OpenAIChatMessage] = []
    for msg in messages:
        wire.append(
            OpenAIChatMessage(
                role=msg.role.value,
                content=msg.content,
                name=msg.name,
                tool_call_id=msg.tool_call_id,
                tool_calls=_domain_tool_calls_to_wire(msg.tool_calls),
                reasoning_content=msg.reasoning_content,
            )
        )
    return wire


def _domain_tools_to_wire(tools: list[ToolDefinition] | None) -> list[OpenAIToolDef] | None:
    if not tools:
        return None
    return [
        OpenAIToolDef(
            type="function",
            function=OpenAIFunctionDef(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters or {"type": "object", "properties": {}},
            ),
        )
        for tool in tools
    ]


def _wire_tool_calls_to_domain(calls: list[OpenAIToolCall] | None) -> list[ToolCall] | None:
    if not calls:
        return None
    return [
        ToolCall(
            id=call.id,
            name=call.function.name,
            arguments=decode_tool_arguments(call.function.arguments),
        )
        for call in calls
    ]


def _wire_usage_to_domain(usage: OpenAIUsage | None) -> Usage:
    """Always return a Usage object (matches prior strategy behavior)."""
    if usage is None:
        return Usage()
    return Usage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )


def _wire_message_to_domain(message: OpenAIResponseMessage) -> ChatMessage:
    try:
        role = Role(message.role)
    except ValueError:
        role = Role.ASSISTANT
    return ChatMessage(
        role=role,
        content=message.content,
        name=message.name,
        tool_call_id=message.tool_call_id,
        tool_calls=_wire_tool_calls_to_domain(message.tool_calls),
        reasoning_content=message.resolved_reasoning_content,
    )


def domain_request_to_wire(
    request: CompletionRequest,
    *,
    default_model: str,
    stream: bool | None = None,
) -> OpenAIChatCompletionRequest:
    return OpenAIChatCompletionRequest(
        model=request.model or default_model,
        messages=_domain_messages_to_wire(request.messages),
        tools=_domain_tools_to_wire(request.tools),
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stop=request.stop,
        stream=stream,
    )


def wire_response_to_domain(wire: OpenAIChatCompletionResponse) -> CompletionResponse:
    if not wire.choices:
        raise InferenceError(f"Malformed OpenAI-compat response: no choices in {wire!r}")
    choice = wire.choices[0]
    return CompletionResponse(
        message=_wire_message_to_domain(choice.message),
        finish_reason=choice.finish_reason,
        usage=_wire_usage_to_domain(wire.usage),
        raw=wire.model_dump(mode="json"),
    )


class OpenAICompatStrategy(InferenceStrategy):
    """HTTP client for any OpenAI Chat Completions compatible endpoint."""

    name = "openai_compat"

    def __init__(self, settings: Settings, *, timeout: float = 120.0) -> None:
        self.base_url = (settings.base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = settings.api_key
        self.default_model = settings.model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._build_headers(None),
        )

    def _build_headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update(extra)
        return headers

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "default_model": self.default_model,
            "auth": "api_key" if self.api_key else "none",
        }

    def _build_body(
        self, request: CompletionRequest, *, stream: bool | None = None
    ) -> dict[str, Any]:
        wire = domain_request_to_wire(
            request, default_model=self.default_model, stream=stream
        )
        body = wire.model_dump(mode="json", exclude_none=True)
        if request.extra:
            body.update(request.extra)
        return body

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        body = self._build_body(request)
        try:
            resp = await self._client.post("/chat/completions", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise InferenceError(f"OpenAI-compat request failed: {exc}") from exc

        try:
            wire = OpenAIChatCompletionResponse.model_validate(resp.json())
            return wire_response_to_domain(wire)
        except InferenceError:
            raise
        except Exception as exc:
            raise InferenceError(
                f"Malformed OpenAI-compat response: {resp.text!r}"
            ) from exc

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        body = self._build_body(request, stream=True)
        try:
            async with self._client.stream("POST", "/chat/completions", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = OpenAIChatCompletionChunk.model_validate_json(payload)
                    except Exception:
                        continue
                    if not chunk.choices:
                        continue
                    text = chunk.choices[0].delta.content
                    if text:
                        yield text
        except httpx.HTTPError as exc:
            raise InferenceError(f"OpenAI-compat stream failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()
