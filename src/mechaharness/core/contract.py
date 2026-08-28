"""OpenAPI-shaped request/response models for the non-DI surface.

CLI, HTTP, and ``mechaharness.factory.run`` share these types so callers who
do not use pyiv still go through one serializable contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    prompt: str
    backend: str | None = None
    family: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    system_prompt: str | None = None
    max_turns: int = 8
    temperature: float | None = None


class RunResponse(BaseModel):
    final_text: str | None
    turns: int
    messages: list[dict[str, Any]]
    events: list[dict[str, Any]] = Field(default_factory=list)
