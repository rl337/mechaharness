"""Parameter models for host CLI verbs (shared by instrumentor + verb catalog)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class InferCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    system: str = ""
    model: str | None = None


class ToolLoopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    tool_name: str = "lookup"
    max_turns: int = 4
    model: str | None = None
    # Product harness family (tool_loop, react, openai_tools, …).
    family: str = "tool_loop"


class RunRecipeCommand(BaseModel):
    """Execute a catalog recipe through a registered recipe adapter."""

    model_config = ConfigDict(extra="forbid")

    name: str
    prompt: str | None = None
    backend: str = "mock"
    family: str = "pass_through"
    max_turns: int = 4
    max_iterations: int = 4
    tool_name: str = "lookup"
    model: str | None = None
    # Optional RecipeBind path or inline soft bindings (context_pack, etc.).
    path: str | None = None
    soft_bindings: dict[str, Any] | None = None


class SetClockCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str  # ISO-8601 UTC


class AdvanceClockCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seconds: float = 0
    minutes: float = 0
    hours: float = 0


__all__ = [
    "AdvanceClockCommand",
    "InferCommand",
    "RunRecipeCommand",
    "SetClockCommand",
    "ToolLoopCommand",
]
