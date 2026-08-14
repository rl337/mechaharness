"""OpenAI-compatible inference strategy.

Covers OpenAI, Azure OpenAI (compat endpoints), Groq, Together, Fireworks,
LM Studio, vLLM, Ollama (OpenAI mode), and most local OpenAI-shaped servers.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
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


def _messages_to_openai(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for msg in messages:
        item: dict[str, Any] = {"role": msg.role.value}
        if msg.content is not None:
            item["content"] = msg.content
        if msg.name is not None:
            item["name"] = msg.name
        if msg.tool_call_id is not None:
            item["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            item["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in msg.tool_calls
            ]
        payload.append(item)
    return payload


def _tools_to_openai(tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


def _parse_tool_calls(raw_calls: list[dict[str, Any]] | None) -> list[ToolCall] | None:
    if not raw_calls:
        return None
    parsed: list[ToolCall] = []
    for call in raw_calls:
        fn = call.get("function") or {}
        arguments = fn.get("arguments") or "{}"
        if isinstance(arguments, str):
            try:
                args_obj = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                args_obj = {"_raw": arguments}
        else:
            args_obj = arguments
        parsed.append(
            ToolCall(
                id=str(call.get("id") or ""),
                name=str(fn.get("name") or ""),
                arguments=args_obj if isinstance(args_obj, dict) else {"value": args_obj},
            )
        )
    return parsed


class OpenAICompatStrategy(InferenceStrategy):
    """HTTP client for any OpenAI Chat Completions compatible endpoint."""

    name = "openai_compat"

    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        default_model: str = "gpt-4o-mini",
        timeout: float = 120.0,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._build_headers(extra_headers),
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

    def _build_body(self, request: CompletionRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": _messages_to_openai(request.messages),
        }
        tools = _tools_to_openai(request.tools)
        if tools:
            body["tools"] = tools
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.stop:
            body["stop"] = request.stop
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

        data = resp.json()
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise InferenceError(f"Malformed OpenAI-compat response: {data!r}") from exc

        usage_raw = data.get("usage") or {}
        return CompletionResponse(
            message=ChatMessage(
                role=Role.ASSISTANT,
                content=message.get("content"),
                tool_calls=_parse_tool_calls(message.get("tool_calls")),
            ),
            finish_reason=choice.get("finish_reason"),
            usage=Usage(
                prompt_tokens=usage_raw.get("prompt_tokens"),
                completion_tokens=usage_raw.get("completion_tokens"),
                total_tokens=usage_raw.get("total_tokens"),
            ),
            raw=data,
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        body = self._build_body(request)
        body["stream"] = True
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
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0].get("delta") or {}
                        text = delta.get("content")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
        except httpx.HTTPError as exc:
            raise InferenceError(f"OpenAI-compat stream failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()


@register_inference("openai")
@register_inference("openai_compat")
def _factory_openai(
    *,
    base_url: str = "https://api.openai.com/v1",
    api_key: str | None = None,
    default_model: str = "gpt-4o-mini",
    **kwargs: Any,
) -> InferenceStrategy:
    return OpenAICompatStrategy(
        base_url=base_url,
        api_key=api_key,
        default_model=default_model,
        **kwargs,
    )


@register_inference("lmstudio")
def _factory_lmstudio(
    *,
    base_url: str = "http://localhost:1234/v1",
    api_key: str | None = "lm-studio",
    default_model: str = "local-model",
    **kwargs: Any,
) -> InferenceStrategy:
    return OpenAICompatStrategy(
        base_url=base_url,
        api_key=api_key,
        default_model=default_model,
        **kwargs,
    )


@register_inference("vllm")
def _factory_vllm(
    *,
    base_url: str = "http://localhost:8000/v1",
    api_key: str | None = None,
    default_model: str = "default",
    **kwargs: Any,
) -> InferenceStrategy:
    return OpenAICompatStrategy(
        base_url=base_url,
        api_key=api_key,
        default_model=default_model,
        **kwargs,
    )


@register_inference("ollama")
def _factory_ollama(
    *,
    base_url: str = "http://localhost:11434/v1",
    api_key: str | None = "ollama",
    default_model: str = "llama3.2",
    **kwargs: Any,
) -> InferenceStrategy:
    return OpenAICompatStrategy(
        base_url=base_url,
        api_key=api_key,
        default_model=default_model,
        **kwargs,
    )
