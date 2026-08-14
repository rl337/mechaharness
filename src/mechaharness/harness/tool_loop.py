"""Generic tool-calling harness family.

Works with any InferenceStrategy that returns structured tool_calls on the
assistant message (OpenAI-compat and Anthropic strategies both do).
"""

from __future__ import annotations

from mechaharness.core.types import ChatMessage
from mechaharness.harness.base import AbstractHarness


class ToolLoopHarness(AbstractHarness):
    """Stop when the model emits no tool calls (final natural-language answer)."""

    family = "tool_loop"

    def should_stop(self, message: ChatMessage, finish_reason: str | None) -> bool:
        if message.tool_calls:
            return False
        if finish_reason in {"tool_calls", "tool_use"}:
            return False
        return True
