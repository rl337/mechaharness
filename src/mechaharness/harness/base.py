"""Harness architecture hierarchy.

``AbstractHarness`` owns the agent loop (template method). Families specialize
prompting, tool-call interpretation, and termination for particular model styles.
Inference is injected via Strategy — harnesses never talk to providers directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from mechaharness.core.exceptions import HarnessError
from mechaharness.core.types import ChatMessage, CompletionRequest, Role, ToolCall, ToolResult
from mechaharness.inference.base import InferenceStrategy
from mechaharness.tools.base import ToolRegistry


class HarnessConfig(BaseModel):
    model: str
    system_prompt: str | None = None
    max_turns: int = 8
    temperature: float | None = None
    max_tokens: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class HarnessEvent(BaseModel):
    """Streaming / observability event emitted during a run."""

    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class HarnessResult(BaseModel):
    final_text: str | None
    messages: list[ChatMessage]
    turns: int
    events: list[HarnessEvent] = Field(default_factory=list)


class AbstractHarness(ABC):
    """Base harness: inject inference + tools, subclasses define the loop policy."""

    family: str = "abstract"

    def __init__(
        self,
        inference: InferenceStrategy,
        tools: ToolRegistry | None = None,
        *,
        config: HarnessConfig,
    ) -> None:
        self.inference = inference
        self.tools = tools or ToolRegistry()
        self.config = config

    async def run(
        self, user_input: str, *, history: list[ChatMessage] | None = None
    ) -> HarnessResult:
        messages = self._bootstrap_messages(user_input, history)
        events: list[HarnessEvent] = []
        turns = 0

        while turns < self.config.max_turns:
            turns += 1
            events.append(HarnessEvent(type="turn_start", data={"turn": turns}))

            request = self.build_request(messages)
            response = await self.inference.complete(request)
            assistant = response.message
            messages.append(assistant)
            events.append(
                HarnessEvent(
                    type="model_response",
                    data={
                        "content": assistant.content,
                        "tool_calls": [tc.model_dump() for tc in (assistant.tool_calls or [])],
                        "finish_reason": response.finish_reason,
                    },
                )
            )

            if self.should_stop(assistant, response.finish_reason):
                return HarnessResult(
                    final_text=assistant.content,
                    messages=messages,
                    turns=turns,
                    events=events,
                )

            tool_results = await self.execute_tools(assistant.tool_calls or [])
            for result in tool_results:
                messages.append(self.tool_result_message(result))
                events.append(
                    HarnessEvent(
                        type="tool_result",
                        data=result.model_dump(),
                    )
                )

            if not tool_results and not self.should_continue_without_tools(assistant):
                return HarnessResult(
                    final_text=assistant.content,
                    messages=messages,
                    turns=turns,
                    events=events,
                )

        raise HarnessError(f"Exceeded max_turns={self.config.max_turns}")

    async def stream_events(
        self, user_input: str, *, history: list[ChatMessage] | None = None
    ) -> AsyncIterator[HarnessEvent]:
        """Convenience wrapper that yields events then a final result event."""
        result = await self.run(user_input, history=history)
        for event in result.events:
            yield event
        yield HarnessEvent(
            type="final",
            data={"final_text": result.final_text, "turns": result.turns},
        )

    def _bootstrap_messages(
        self, user_input: str, history: list[ChatMessage] | None
    ) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        if self.config.system_prompt:
            messages.append(ChatMessage(role=Role.SYSTEM, content=self.config.system_prompt))
        if history:
            messages.extend(history)
        messages.append(ChatMessage(role=Role.USER, content=user_input))
        return messages

    def build_request(self, messages: list[ChatMessage]) -> CompletionRequest:
        """Hook: families can reshape messages / tool schemas per model quirks."""
        return CompletionRequest(
            model=self.config.model,
            messages=messages,
            tools=self.tools.definitions() or None,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            extra=self.config.extra,
        )

    @abstractmethod
    def should_stop(self, message: ChatMessage, finish_reason: str | None) -> bool:
        """Return True when the harness should end the loop."""

    def should_continue_without_tools(self, message: ChatMessage) -> bool:
        return False

    async def execute_tools(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in tool_calls:
            if call.name not in self.tools:
                results.append(
                    ToolResult(
                        tool_call_id=call.id,
                        content=f"Unknown tool: {call.name}",
                        is_error=True,
                    )
                )
                continue
            results.append(await self.tools.execute(call.name, call.arguments, call.id))
        return results

    def tool_result_message(self, result: ToolResult) -> ChatMessage:
        """Hook: families may encode tool results differently."""
        return ChatMessage(
            role=Role.TOOL,
            content=result.content,
            tool_call_id=result.tool_call_id,
        )
