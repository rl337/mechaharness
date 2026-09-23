"""Inference Strategy: pluggable backends for raw model calls.

Client code depends on ``InferenceStrategy``, not on a specific provider.
Concrete strategies adapt OpenAI, Anthropic, LM Studio, vLLM, etc.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from mechaharness.core.access import CapabilityProfile, default_capability_profile
from mechaharness.core.completer import Completer
from mechaharness.core.types import CompletionRequest, CompletionResponse


class InferenceStrategy(Completer):
    """Strategy interface for talking to an inference engine."""

    name: str = "base"

    def capability_profile(self) -> CapabilityProfile:
        """Declared skills used for cost pricing of this backend."""
        return default_capability_profile()

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Run a single non-streaming completion."""

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Optional token stream. Default falls back to a single complete()."""
        response = await self.complete(request)
        text = response.message.content or ""
        if text:
            yield text

    async def aclose(self) -> None:  # noqa: B027 - optional cleanup hook
        """Release network resources. Override when the strategy holds a client."""

    def describe(self) -> dict[str, Any]:
        """Machine-readable metadata for CLI/API introspection."""
        return {"name": self.name}
