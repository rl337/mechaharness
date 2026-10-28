"""User-story suite schema (shared setup/vars + parallel|sequential execution)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SuiteExecution(BaseModel):
    """How stages share a workspace and whether order is required."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["parallel", "sequential"] = "parallel"
    ordered: bool = False

    @model_validator(mode="after")
    def _ordered_only_sequential(self) -> SuiteExecution:
        if self.ordered and self.mode != "sequential":
            raise ValueError("execution.ordered requires execution.mode=sequential")
        return self


class SuiteStage(BaseModel):
    """One story scenario membership row."""

    model_config = ConfigDict(extra="forbid")

    story: str
    scenario: str


class SuiteSpec(BaseModel):
    """Catalog entry under ``suites/<id>/suite.json``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    persona: str
    execution: SuiteExecution = Field(default_factory=SuiteExecution)
    vars: dict[str, Any] = Field(default_factory=dict)
    setup: list[str] = Field(default_factory=list)
    cleanup: list[str] = Field(default_factory=list)
    workspace: str | None = None
    stages: list[SuiteStage] = Field(min_length=1)

    @model_validator(mode="after")
    def _stage_keys_unique(self) -> SuiteSpec:
        seen: set[tuple[str, str]] = set()
        for stage in self.stages:
            key = (stage.story, stage.scenario)
            if key in seen:
                raise ValueError(
                    f"duplicate stage {stage.story!r}/{stage.scenario!r}"
                )
            seen.add(key)
        return self


__all__ = [
    "SuiteExecution",
    "SuiteSpec",
    "SuiteStage",
]
