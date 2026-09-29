"""Satisfactory-completion contracts distinct from 'answer generated'."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CompletionState = Literal[
    "incomplete",
    "answer_generated",
    "verified",
    "complete",
    "failed",
]


class OutcomeContract(BaseModel):
    """Machine-readable definition of task completion (not mere generation)."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    acceptance: list[str] = Field(default_factory=list)
    require_verification: bool = False
    verification_refs: list[str] = Field(default_factory=list)
    allow_answer_without_complete: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def evaluate(
        self,
        *,
        answer_generated: bool = False,
        verification_passed: bool | None = None,
        acceptance_met: bool | None = None,
    ) -> CompletionState:
        if acceptance_met is False:
            return "failed"
        if self.require_verification:
            if verification_passed is False:
                return "failed"
            if verification_passed is not True:
                if answer_generated:
                    return "answer_generated"
                return "incomplete"
            if acceptance_met is True or acceptance_met is None:
                return "complete"
            return "verified"
        if acceptance_met is True:
            return "complete"
        if answer_generated:
            return "answer_generated" if self.allow_answer_without_complete else "incomplete"
        return "incomplete"
