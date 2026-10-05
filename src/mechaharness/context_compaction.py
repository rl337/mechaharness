"""Staged, pluggable context compaction with discard provenance.

WalkingLabs L05 and frontier designs (Claude Code / Pi) describe staged
compaction: lossless prune, structured distill, then optional lossy summary
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-05-why-long-running-tasks-lose-continuity/,
https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/claude-code/).

MechaHarness provides a strategy ABC and a default staged pipeline::

    >>> from mechaharness.context_compaction import (
    ...     DefaultStagedCompaction, CompactionInput,
    ... )
    >>> strategy = DefaultStagedCompaction()
    >>> result = strategy.compact(CompactionInput(
    ...     messages=[
    ...         {"role": "user", "content": "a"},
    ...         {"role": "user", "content": "a"},
    ...         {"role": "assistant", "content": "long " * 50},
    ...     ]
    ... ))
    >>> "deduplicated" in result.discarded_classes
    True
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CompactionStage = Literal["lossless", "distill", "lossy"]


class CompactionInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    messages: list[dict[str, Any]] = Field(default_factory=list)
    max_messages: int | None = None
    max_chars: int | None = None


class CompactionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    messages: list[dict[str, Any]] = Field(default_factory=list)
    stages_applied: list[CompactionStage] = Field(default_factory=list)
    discarded_classes: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ContextCompactionStrategy(ABC):
    @abstractmethod
    def compact(self, inp: CompactionInput) -> CompactionResult:
        raise NotImplementedError


class DefaultStagedCompaction(ContextCompactionStrategy):
    """Lossless dedupe → distill truncations → optional lossy drop of oldest."""

    def compact(self, inp: CompactionInput) -> CompactionResult:
        messages = [dict(m) for m in inp.messages]
        stages: list[CompactionStage] = []
        discarded: list[str] = []

        # Lossless: drop exact duplicate adjacent user contents
        deduped: list[dict[str, Any]] = []
        for msg in messages:
            if (
                deduped
                and deduped[-1].get("role") == msg.get("role")
                and deduped[-1].get("content") == msg.get("content")
            ):
                discarded.append("deduplicated")
                continue
            deduped.append(msg)
        if len(deduped) != len(messages):
            stages.append("lossless")
        messages = deduped

        # Distill: truncate very long contents
        distilled: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str) and len(content) > 200:
                distilled.append({**msg, "content": content[:200] + "…"})
                discarded.append("truncated_content")
            else:
                distilled.append(msg)
        if any(c == "truncated_content" for c in discarded):
            stages.append("distill")
        messages = distilled

        # Lossy: drop oldest beyond max_messages
        if inp.max_messages is not None and len(messages) > inp.max_messages:
            drop = len(messages) - inp.max_messages
            messages = messages[drop:]
            discarded.extend(["dropped_oldest"] * drop)
            stages.append("lossy")

        return CompactionResult(
            messages=messages,
            stages_applied=stages,
            discarded_classes=sorted(set(discarded)),
            provenance={"strategy": "default_staged"},
        )
