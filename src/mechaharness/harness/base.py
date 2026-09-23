"""Harness architecture hierarchy.

``AbstractHarness`` is an agent: one ``run()`` is a finite lifecycle of
inference calls. Families specialize prompting, tool-call interpretation, and
termination. The shared loop emits EventLog records, prices cost, and checks
tool grants. Inference is injected via Strategy — harnesses never talk to
providers directly.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from mechaharness.core import events as core_events
from mechaharness.core.access import (
    AccessControl,
    AccessPolicy,
    CapabilityProfile,
    CostAccountant,
    CostReport,
    InMemoryAccessControl,
    InMemoryCostAccountant,
)
from mechaharness.core.completer import Completer
from mechaharness.core.events import (
    AgentEnd,
    AgentStart,
    Event,
    EventLog,
    EventType,
    Inference,
    MaxTurns,
    RunEnd,
    RunStart,
    TurnStart,
    default_event_log,
    event_type_key,
)
from mechaharness.core.exceptions import HarnessError
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    ToolCall,
    ToolResult,
)
from mechaharness.tools.base import ToolRegistry
from mechaharness.tools.subagents import install_subagent_tools


class HarnessConfig(BaseModel):
    """Per-run knobs for a harness (model, turn budget, sampling)."""

    model: str
    system_prompt: str | None = None
    max_turns: int = 8
    temperature: float | None = None
    max_tokens: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class HarnessResult(BaseModel):
    """Outcome of ``AbstractHarness.run``: final text, transcript, events, cost."""

    final_text: str | None
    messages: list[ChatMessage]
    turns: int
    events: list[Event] = Field(default_factory=list)
    cost: CostReport = Field(default_factory=CostReport)


class AbstractHarness(Completer):
    """Base harness: inject a completer + tools, subclasses define the loop policy."""

    family: str = "abstract"

    def __init__(
        self,
        inference: Completer,
        tools: ToolRegistry | None = None,
        *,
        config: HarnessConfig,
        event_log: EventLog | None = None,
        access: AccessControl | AccessPolicy | None = None,
        cost: CostAccountant | None = None,
        agent_id: str | None = None,
        parent_agent_id: str | None = None,
        subagent_tools: bool = False,
    ) -> None:
        self.inference = inference
        self.tools = tools or ToolRegistry()
        self.config = config
        self.event_log = event_log or default_event_log()
        self.agent_id = agent_id or str(uuid4())
        self.parent_agent_id = parent_agent_id
        if isinstance(access, AccessPolicy):
            access = InMemoryAccessControl(event_log=self.event_log, policy=access)
        self.access = access or InMemoryAccessControl(event_log=self.event_log)
        self.cost = cost or InMemoryCostAccountant(event_log=self.event_log)
        if subagent_tools:
            install_subagent_tools(self.tools, self.event_log, self.agent_id)

    def capability_profile(self) -> CapabilityProfile:
        return self.inference.capability_profile()

    def access_policy(self) -> AccessPolicy:
        table = getattr(self.access, "policy", None)
        if table is not None:
            return AccessPolicy(grants=list(table.grants))
        return AccessPolicy()

    def _emit(self, event_type: type[EventType], payload: dict[str, Any], run_id: str) -> None:
        self.event_log.emit(
            Event(
                type=event_type_key(event_type),
                agent_id=self.agent_id,
                parent_agent_id=self.parent_agent_id,
                run_id=run_id,
                payload=payload,
            )
        )

    def _completer_name(self) -> str:
        return str(
            getattr(self.inference, "name", None)
            or getattr(self.inference, "family", None)
            or self.family
        )

    def _link_child_completer(self) -> None:
        child = self.inference
        if not isinstance(child, AbstractHarness):
            return
        if child.parent_agent_id is None:
            child.parent_agent_id = self.agent_id
        if child.event_log is not self.event_log:
            child.event_log = self.event_log

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Treat this harness as a completer (same shape as a raw model)."""
        user_indices = [i for i, msg in enumerate(request.messages) if msg.role == Role.USER]
        if user_indices:
            last = user_indices[-1]
            user_input = request.messages[last].content or ""
            history = request.messages[:last]
        else:
            user_input = ""
            history = list(request.messages)
        result = await self.run(user_input, history=history or None)
        return CompletionResponse(
            message=ChatMessage(role=Role.ASSISTANT, content=result.final_text),
            finish_reason="stop",
            cost=result.cost,
        )

    async def run(
        self, user_input: str, *, history: list[ChatMessage] | None = None
    ) -> HarnessResult:
        """Run one agent lifecycle for ``user_input`` and return the result.

        Emits EventLog records, prices inference/tools via ``CostAccountant``,
        and enforces tool grants through ``AccessControl``.
        """
        self._link_child_completer()
        run_id = str(uuid4())
        run_cost = CostReport()
        self._emit(
            AgentStart,
            {
                "family": self.family,
                "label": self.family,
                "model": self.config.model,
                "tools": [item.name for item in self.tools.definitions()],
                "parent_agent_id": self.parent_agent_id,
            },
            run_id,
        )
        self._emit(RunStart, {"prompt_chars": len(user_input)}, run_id)
        try:
            result = await self._run_loop(user_input, history, run_id, run_cost)
        except HarnessError:
            self._emit(MaxTurns, {"max_turns": self.config.max_turns}, run_id)
            self._emit(
                RunEnd,
                {
                    "status": "max_turns",
                    "turns": self.config.max_turns,
                    "has_final_text": False,
                },
                run_id,
            )
            self._emit(AgentEnd, {"status": "max_turns"}, run_id)
            raise
        self._emit(
            RunEnd,
            {
                "status": "ok",
                "turns": result.turns,
                "has_final_text": result.final_text is not None,
            },
            run_id,
        )
        self._emit(AgentEnd, {"status": "ok"}, run_id)
        result.events = self.event_log.query(run_id=run_id)
        result.cost = run_cost
        return result

    async def _run_loop(
        self,
        user_input: str,
        history: list[ChatMessage] | None,
        run_id: str,
        cost: CostReport,
    ) -> HarnessResult:
        messages = self._bootstrap_messages(user_input, history)
        turns = 0

        while turns < self.config.max_turns:
            turns += 1
            self._emit(TurnStart, {"turn": turns}, run_id)

            request = self.build_request(messages)
            response = await self.inference.complete(request)
            nested_cost = response.cost
            if nested_cost is not None and getattr(nested_cost, "entries", None):
                for nested_entry in nested_cost.entries:
                    cost.add(nested_entry)
            else:
                entry = self.cost.price_inference(
                    self._completer_name(),
                    self.capability_profile(),
                    agent_id=self.agent_id,
                    run_id=run_id,
                    parent_agent_id=self.parent_agent_id,
                    usage=response.usage,
                )
                cost.add(entry)
            assistant = response.message
            messages.append(assistant)
            inference_payload: dict[str, Any] = {
                "completer": self._completer_name(),
                "model": request.model,
                "finish_reason": response.finish_reason,
                "content": assistant.content,
                "tool_calls": [tc.model_dump() for tc in (assistant.tool_calls or [])],
            }
            if assistant.reasoning_content:
                inference_payload["reasoning_content"] = assistant.reasoning_content
            if response.usage is not None:
                inference_payload["usage"] = response.usage.model_dump()
            self._emit(Inference, inference_payload, run_id)

            if self.should_stop(assistant, response.finish_reason):
                return HarnessResult(
                    final_text=self.final_text(assistant),
                    messages=messages,
                    turns=turns,
                    cost=cost,
                )

            tool_calls = self.interpret_tool_calls(assistant, turn=turns)
            tool_results = await self.execute_tools(tool_calls, cost=cost, run_id=run_id)
            for result in tool_results:
                messages.append(self.tool_result_message(result))

            if not tool_results and not self.should_continue_without_tools(assistant):
                return HarnessResult(
                    final_text=self.final_text(assistant),
                    messages=messages,
                    turns=turns,
                    cost=cost,
                )

        raise HarnessError(f"Exceeded max_turns={self.config.max_turns}")

    async def stream_events(
        self, user_input: str, *, history: list[ChatMessage] | None = None
    ) -> AsyncIterator[Event]:
        result = await self.run(user_input, history=history)
        for event in result.events:
            yield event

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

    def final_text(self, message: ChatMessage) -> str | None:
        """Hook: families may extract a shorter answer from the last message."""
        return message.content

    def interpret_tool_calls(self, message: ChatMessage, *, turn: int) -> list[ToolCall]:
        """Hook: families may parse tool calls from free-form text."""
        del turn
        return list(message.tool_calls or [])

    async def execute_tools(
        self,
        tool_calls: list[ToolCall],
        *,
        run_id: str,
        cost: CostReport,
    ) -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in tool_calls:
            self._emit(
                core_events.ToolCall,
                {"name": call.name, "tool_call_id": call.id, "arguments": call.arguments},
                run_id,
            )
            if call.name not in self.tools:
                result = ToolResult(
                    tool_call_id=call.id,
                    content=f"Unknown tool: {call.name}",
                    is_error=True,
                )
                results.append(result)
                self._emit_tool_result(result, run_id, name=call.name)
                continue
            tool = self.tools.get(call.name)
            if not self.access.allows(
                tool.grants,
                tool_name=tool.name,
                agent_id=self.agent_id,
                run_id=run_id,
                parent_agent_id=self.parent_agent_id,
            ):
                needed = ", ".join(tool.grants) or "(none)"
                result = ToolResult(
                    tool_call_id=call.id,
                    content=f"Permission denied for {tool.name}: requires {needed}",
                    is_error=True,
                )
                results.append(result)
                self._emit_tool_result(result, run_id, name=tool.name)
                continue
            result = await self.tools.execute(call.name, call.arguments, call.id)
            cost.add(
                self.cost.price_tool(
                    tool.name,
                    tool.ability,
                    agent_id=self.agent_id,
                    run_id=run_id,
                    parent_agent_id=self.parent_agent_id,
                )
            )
            results.append(result)
            self._emit_tool_result(result, run_id, name=tool.name)
        return results

    def _emit_tool_result(self, result: ToolResult, run_id: str, *, name: str) -> None:
        self._emit(
            core_events.ToolResult,
            {
                "name": name,
                "tool_call_id": result.tool_call_id,
                "is_error": result.is_error,
                "content": result.content,
            },
            run_id,
        )

    def tool_result_message(self, result: ToolResult) -> ChatMessage:
        """Hook: families may encode tool results differently."""
        return ChatMessage(
            role=Role.TOOL,
            content=result.content,
            tool_call_id=result.tool_call_id,
        )
