"""Tagged inference outcomes by call kind.

| Kind | Type | Typical producer |
|------|------|------------------|
| Generative chat / tools | ``Completion`` | ``InferenceStrategy.complete`` |
| Judge / System One | ``Judgement`` | ``judge()`` |
| Media / artifacts | ``Generation`` | host Comfy (and future media adapters) |

``AccessPolicy`` gates tools and lanes. ``JudgementPolicy`` maps a ``Judgement``
to a verdict enum. Keep those axes separate.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.types import CompletionResponse

# Generative chat / tool-loop outcome (existing domain type under a clear name).
Completion = CompletionResponse


class Generation(BaseModel):
    """Media / artifact-producing outcome.

    Placeholder for ComfyUI (and similar) results. Hosts may populate ``paths``
    after ``comfy_fetch_artifact``; library adapters can adopt this shape later.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = Field(default="1", alias="schemaVersion")
    kind: Literal["generation"] = "generation"
    prompt_id: str | None = Field(default=None, alias="promptId")
    paths: list[str] = Field(default_factory=list)
    content_type: str | None = Field(default=None, alias="contentType")
    bytes: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


__all__ = [
    "Completion",
    "CompletionResponse",
    "Generation",
]
