"""Anthropic Messages API inference strategy."""

from __future__ import annotations

from typing import Any

import httpx

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
from mechaharness.inference.registry import register_inference


def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == Role.SYSTEM:
            if msg.content:
                system_parts.append(msg.content)
            continue

        if msg.role == Role.TOOL:
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content or "",
                        }
                    ],
                }
            )
            continue

        if msg.role == Role.ASSISTANT and msg.tool_calls:
            content: list[dict[str, Any]] = []
            if msg.content:
                content.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    }
                )
            converted.append({"role": "assistant", "content": content})
            continue

        converted.append(
            {
                "role": "user" if msg.role == Role.USER else "assistant",
                "content": msg.content or "",
            }
        )

    system = "\n\n".join(system_parts) if system_parts else None
    return system, converted


def _tools_to_anthropic(tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters or {"type": "object", "properties": {}},
        }
        for tool in tools
    ]


class AnthropicStrategy(InferenceStrategy):
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        default_model: str = "claude-sonnet-4-5",
        api_version: str = "2023-06-01",
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "x-api-key": api_key,
                "anthropic-version": api_version,
                "content-type": "application/json",
            },
        )

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "default_model": self.default_model,
            "auth": "api_key",
        }

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        system, messages = _split_system(request.messages)
        body: dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
        }
        if system:
            body["system"] = system
        tools = _tools_to_anthropic(request.tools)
        if tools:
            body["tools"] = tools
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.stop:
            body["stop_sequences"] = request.stop
        if request.extra:
            body.update(request.extra)

        try:
            resp = await self._client.post("/v1/messages", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise InferenceError(f"Anthropic request failed: {exc}") from exc

        data = resp.json()
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(str(block.get("text") or ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=str(block.get("id") or ""),
                        name=str(block.get("name") or ""),
                        arguments=block.get("input") or {},
                    )
                )

        usage_raw = data.get("usage") or {}
        return CompletionResponse(
            message=ChatMessage(
                role=Role.ASSISTANT,
                content="\n".join(text_parts) if text_parts else None,
                tool_calls=tool_calls or None,
            ),
            finish_reason=data.get("stop_reason"),
            usage=Usage(
                prompt_tokens=usage_raw.get("input_tokens"),
                completion_tokens=usage_raw.get("output_tokens"),
                total_tokens=(
                    (usage_raw.get("input_tokens") or 0) + (usage_raw.get("output_tokens") or 0)
                    if usage_raw
                    else None
                ),
            ),
            raw=data,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


@register_inference("anthropic")
def _factory_anthropic(
    *,
    api_key: str,
    base_url: str = "https://api.anthropic.com",
    default_model: str = "claude-sonnet-4-5",
    **kwargs: Any,
) -> InferenceStrategy:
    return AnthropicStrategy(
        api_key=api_key,
        base_url=base_url,
        default_model=default_model,
        **kwargs,
    )
