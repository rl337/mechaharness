"""One-shot harness: a single inference call, then stop.

Used to verify EventLog + cost wiring without a tool loop.
"""

from __future__ import annotations

from mechaharness.core.types import ChatMessage, CompletionRequest
from mechaharness.harness.base import AbstractHarness


class PassThroughHarness(AbstractHarness):
    """Forward the prompt to the completer once and return its text."""

    family = "pass_through"

    def build_request(self, messages: list[ChatMessage]) -> CompletionRequest:
        return CompletionRequest(
            model=self.config.model,
            messages=messages,
            tools=None,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            extra=self.config.extra,
        )

    def should_stop(self, message: ChatMessage, finish_reason: str | None) -> bool:
        return True
