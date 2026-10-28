"""Authored suite.yaml schema (no stages list — stages live as YAML files)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tests.stories.suite_spec import SuiteExecution


class SuiteAuthorSpec(BaseModel):
    """Human-authored ``suites/<id>/suite.yaml`` (stages discovered from disk)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    persona: str
    execution: SuiteExecution = Field(default_factory=SuiteExecution)
    vars: dict[str, Any] = Field(default_factory=dict)
    setup: list[str] = Field(default_factory=list)
    cleanup: list[str] = Field(default_factory=list)
    # Shared workspace policy for sequential arcs (temp | absolute | relative).
    workspace: str | None = None
    # Optional path (relative to suite dir) whose tree materializes into files.json.
    sources: str | None = None

    @model_validator(mode="after")
    def _id_nonempty(self) -> SuiteAuthorSpec:
        if not self.id.strip():
            raise ValueError("suite id must be non-empty")
        return self


__all__ = ["SuiteAuthorSpec"]
