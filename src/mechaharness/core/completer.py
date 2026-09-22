"""Shared completer interface: a raw model and a harness are the same call shape."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mechaharness.core.access import AccessPolicy, CapabilityProfile
from mechaharness.core.types import CompletionRequest, CompletionResponse


class Completer(ABC):
    """Something that can answer a ``CompletionRequest``.

    Inference backends and harnesses both implement this so callers do not
    distinguish a raw model from a nested harness.
    """

    @abstractmethod
    def capability_profile(self) -> CapabilityProfile:
        """Skills (and therefore inference cost) of this completer."""

    def access_policy(self) -> AccessPolicy:
        """Tool grants. Models default to none; harnesses override."""
        return AccessPolicy()

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Run one completion (a model call or a full harness run)."""
