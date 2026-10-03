"""Classic ReAct-style harness using textual Thought/Action/Observation turns.

Useful for models without reliable native tool-calling, or for teaching /
debugging agent loops with transparent traces. The shared ``AbstractHarness``
loop owns EventLog, cost, and access; this family only parses Action blocks
and Observation messages.
"""

from __future__ import annotations

import json
import re

from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import AccessControl, CostAccountant
from mechaharness.core.completer import Completer
from mechaharness.core.environment import InferenceEnvironment
from mechaharness.core.events import EventLog
from mechaharness.core.types import ChatMessage, CompletionRequest, Role, ToolCall, ToolResult
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.lifecycle_extension import LifecycleExtensionRegistry
from mechaharness.tools.base import ToolRegistry

_ACTION_RE = re.compile(
    r"Action\s*:\s*(?P<name>[A-Za-z0-9_\-]+)\s*\n"
    r"Action Input\s*:\s*(?P<input>.*?)(?=\nObservation:|\nThought:|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_FINAL_RE = re.compile(r"Final Answer\s*:\s*(?P<answer>.+)\Z", re.DOTALL | re.IGNORECASE)


class ReactHarness(AbstractHarness):
    family = "react"

    DEFAULT_SYSTEM = (
        "You are an agent that solves tasks with tools using this format:\n"
        "Thought: reason about the next step\n"
        "Action: tool_name\n"
        "Action Input: {json arguments}\n"
        "Observation: (filled by the system)\n"
        "... (repeat as needed)\n"
        "Thought: I know the answer\n"
        "Final Answer: the answer for the user\n"
    )

    def __init__(
        self,
        inference: Completer,
        tools: ToolRegistry,
        *,
        config: HarnessConfig,
        event_log: EventLog,
        access: AccessControl,
        cost: CostAccountant,
        environment: InferenceEnvironment,
        lifecycle_extensions: LifecycleExtensionRegistry | None = None,
        capability_envelope: CapabilityEnvelope | None = None,
        agent_id: str | None = None,
        parent_agent_id: str | None = None,
    ) -> None:
        super().__init__(
            inference,
            tools,
            config=config,
            event_log=event_log,
            access=access,
            cost=cost,
            environment=environment,
            lifecycle_extensions=lifecycle_extensions,
            capability_envelope=capability_envelope,
            agent_id=agent_id,
            parent_agent_id=parent_agent_id,
        )
        if not self.config.system_prompt:
            tool_lines = "\n".join(
                f"- {t.name}: {t.description}" for t in self.tools.definitions()
            )
            self.config.system_prompt = (
                self.DEFAULT_SYSTEM + "\nAvailable tools:\n" + (tool_lines or "(none)")
            )

    def build_request(self, messages: list[ChatMessage]) -> CompletionRequest:
        # ReAct uses free-form text; do not send native tool schemas.
        return CompletionRequest(
            model=self.config.model,
            messages=messages,
            tools=None,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            extra=self.config.extra,
        )

    def should_stop(self, message: ChatMessage, finish_reason: str | None) -> bool:
        del finish_reason
        text = message.content or ""
        return not bool(_ACTION_RE.search(text))

    def final_text(self, message: ChatMessage) -> str | None:
        text = message.content or ""
        final = _FINAL_RE.search(text)
        if final and not _ACTION_RE.search(text):
            return final.group("answer").strip()
        return text

    def interpret_tool_calls(self, message: ChatMessage, *, turn: int) -> list[ToolCall]:
        match = _ACTION_RE.search(message.content or "")
        if not match:
            return []
        raw_input = match.group("input").strip()
        try:
            arguments = json.loads(raw_input)
            if not isinstance(arguments, dict):
                arguments = {"value": arguments}
        except json.JSONDecodeError:
            arguments = {"input": raw_input}
        return [ToolCall(id=f"react-{turn}", name=match.group("name"), arguments=arguments)]

    def tool_result_message(self, result: ToolResult) -> ChatMessage:
        return ChatMessage(
            role=Role.USER,
            content=f"Observation: {result.content}",
        )
