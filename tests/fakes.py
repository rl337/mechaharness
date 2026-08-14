"""Test doubles."""

from __future__ import annotations

from mechaharness.core.types import ChatMessage, CompletionRequest, CompletionResponse, Role
from mechaharness.inference.base import InferenceStrategy


class ScriptedInference(InferenceStrategy):
    """Returns a predetermined sequence of assistant messages."""

    name = "scripted"

    def __init__(self, responses: list[ChatMessage]) -> None:
        self._responses = list(responses)
        self.requests: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        if not self._responses:
            return CompletionResponse(
                message=ChatMessage(role=Role.ASSISTANT, content="(no scripted response left)"),
                finish_reason="stop",
            )
        message = self._responses.pop(0)
        finish = "tool_calls" if message.tool_calls else "stop"
        return CompletionResponse(message=message, finish_reason=finish)
