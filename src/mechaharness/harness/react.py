"""Classic ReAct-style harness using textual Thought/Action/Observation turns.

Useful for models without reliable native tool-calling, or for teaching /
debugging agent loops with transparent traces.
"""

from __future__ import annotations

import json
import re
from typing import Any

from mechaharness.core.types import ChatMessage, CompletionRequest, Role, ToolCall
from mechaharness.harness.base import AbstractHarness, HarnessResult

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
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
        text = message.content or ""
        return bool(_FINAL_RE.search(text))

    def should_continue_without_tools(self, message: ChatMessage) -> bool:
        return True

    async def run(
        self, user_input: str, *, history: list[ChatMessage] | None = None
    ) -> HarnessResult:
        # Override lightly: parse Action blocks into synthetic tool calls.
        messages = self._bootstrap_messages(user_input, history)
        events = []
        turns = 0

        while turns < self.config.max_turns:
            turns += 1
            request = self.build_request(messages)
            response = await self.inference.complete(request)
            assistant = response.message
            messages.append(assistant)

            text = assistant.content or ""
            final = _FINAL_RE.search(text)
            if final and not _ACTION_RE.search(text):
                return HarnessResult(
                    final_text=final.group("answer").strip(),
                    messages=messages,
                    turns=turns,
                    events=events,
                )

            match = _ACTION_RE.search(text)
            if not match:
                return HarnessResult(
                    final_text=text,
                    messages=messages,
                    turns=turns,
                    events=events,
                )

            raw_input = match.group("input").strip()
            try:
                arguments = json.loads(raw_input)
                if not isinstance(arguments, dict):
                    arguments = {"value": arguments}
            except json.JSONDecodeError:
                arguments = {"input": raw_input}

            call = ToolCall(id=f"react-{turns}", name=match.group("name"), arguments=arguments)
            results = await self.execute_tools([call])
            observation = results[0].content if results else ""
            messages.append(
                ChatMessage(
                    role=Role.USER,
                    content=f"Observation: {observation}",
                )
            )

        from mechaharness.core.exceptions import HarnessError

        raise HarnessError(f"Exceeded max_turns={self.config.max_turns}")
