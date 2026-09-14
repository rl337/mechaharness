"""In-process mock completer for tests and CI (no network)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from mechaharness.config import Settings
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    Usage,
)
from mechaharness.inference.base import InferenceStrategy


class MockInferenceStrategy(InferenceStrategy):
    """Echo the last user message. Safe default for ``--backend mock``."""

    name = "mock"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "network": False}

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        last_user = ""
        for message in reversed(request.messages):
            if message.role == Role.USER and message.content:
                last_user = message.content
                break
        return CompletionResponse(
            message=ChatMessage(role=Role.ASSISTANT, content=f"mock reply: {last_user}"),
            finish_reason="stop",
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        response = await self.complete(request)
        text = response.message.content or ""
        if text:
            yield text
