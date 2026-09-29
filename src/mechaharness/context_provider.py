"""Lazy, provenance-bearing context providers.

Hosts (e.g. June document manager / knowledge graph) implement providers.
MechaHarness consumes them through envelopes and context compilation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContextIndexEntry(BaseModel):
    """Discoverable description before loading a large payload."""

    model_config = ConfigDict(extra="allow")

    ref: str
    title: str = ""
    summary: str = ""
    token_estimate: int | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class ContextChunk(BaseModel):
    """Scoped context payload with provenance and cost attribution."""

    model_config = ConfigDict(extra="allow")

    ref: str
    content: str
    provider_id: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    token_estimate: int | None = None
    scope: str = "task"


class ContextProvider(ABC):
    """Lazily supplies scoped, provenance-bearing context."""

    @abstractmethod
    def provider_id(self) -> str:
        ...

    @abstractmethod
    def index(self, *, query: str | None = None, budget: int = 32) -> list[ContextIndexEntry]:
        """Return discoverable descriptions before loading large payloads."""

    @abstractmethod
    def load(self, refs: Sequence[str]) -> list[ContextChunk]:
        """Load selected refs just in time."""


class StaticContextProvider(ContextProvider):
    """In-memory provider for tests and simple host bindings."""

    def __init__(
        self,
        provider_id: str,
        entries: Mapping[str, str],
        *,
        summaries: Mapping[str, str] | None = None,
    ) -> None:
        self._id = provider_id
        self._entries = dict(entries)
        self._summaries = dict(summaries or {})

    def provider_id(self) -> str:
        return self._id

    def index(self, *, query: str | None = None, budget: int = 32) -> list[ContextIndexEntry]:
        items: list[ContextIndexEntry] = []
        q = (query or "").lower()
        for ref, content in self._entries.items():
            if q and q not in ref.lower() and q not in content.lower():
                continue
            items.append(
                ContextIndexEntry(
                    ref=ref,
                    title=ref,
                    summary=self._summaries.get(ref, content[:120]),
                    token_estimate=max(1, len(content) // 4),
                    provenance={"provider": self._id},
                )
            )
            if len(items) >= budget:
                break
        return items

    def load(self, refs: Sequence[str]) -> list[ContextChunk]:
        out: list[ContextChunk] = []
        for ref in refs:
            content = self._entries.get(ref)
            if content is None:
                continue
            out.append(
                ContextChunk(
                    ref=ref,
                    content=content,
                    provider_id=self._id,
                    provenance={"provider": self._id},
                    token_estimate=max(1, len(content) // 4),
                )
            )
        return out


class ContextProviderRegistry:
    """Host-populated map of context providers."""

    def __init__(self, providers: Sequence[ContextProvider] | None = None) -> None:
        self._by_id: dict[str, ContextProvider] = {}
        for provider in providers or []:
            self.register(provider)

    def register(self, provider: ContextProvider) -> None:
        self._by_id[provider.provider_id()] = provider

    def get(self, provider_id: str) -> ContextProvider | None:
        return self._by_id.get(provider_id)

    def ids(self) -> list[str]:
        return sorted(self._by_id)
