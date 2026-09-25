"""Named decision-plane surfaces over JDG types (POL-01)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.inference.judge import (
    ChoiceQuestion,
    ChoiceSignal,
    NoulQuestion,
    NoulSignal,
    Question,
    ScoreQuestion,
    ScoreSignal,
    Signal,
)


DecisionSurfaceKind = Literal["choice", "score", "noul"]


class DecisionSurface(BaseModel):
    """MechaHarness-owned decision surface declaration."""

    model_config = ConfigDict(extra="allow")

    kind: DecisionSurfaceKind
    question: Question
    allowed_actions: list[str] = Field(default_factory=list)


class DecisionSurfaceResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: DecisionSurfaceKind
    signal: Signal
    source: Literal["rules", "inference"] = "inference"
    rejected: bool = False
    reject_reason: str | None = None


class DecisionSurfaceBackend(Protocol):
    """Adapter protocol — rules or inference may implement subsets."""

    async def evaluate(
        self, surface: DecisionSurface, *, state: Mapping[str, Any]
    ) -> DecisionSurfaceResult: ...


class RulesDecisionBackend:
    """Deterministic rules backend; distinguishable from learned signals."""

    def __init__(self, answers: Mapping[str, Any] | None = None) -> None:
        self.answers = dict(answers or {})

    async def evaluate(
        self, surface: DecisionSurface, *, state: Mapping[str, Any]
    ) -> DecisionSurfaceResult:
        _ = state
        q = surface.question
        raw = self.answers.get(q.id)
        if isinstance(q, ChoiceQuestion):
            selected = str(raw) if raw is not None else q.options[0].id
            if surface.allowed_actions and selected not in surface.allowed_actions:
                return DecisionSurfaceResult(
                    kind="choice",
                    signal=ChoiceSignal(
                        id=q.id,
                        selected=selected,
                        probabilities={selected: 1.0},
                    ),
                    source="rules",
                    rejected=True,
                    reject_reason="choice_not_allowed",
                )
            return DecisionSurfaceResult(
                kind="choice",
                signal=ChoiceSignal(
                    id=q.id,
                    selected=selected,
                    probabilities={o.id: (1.0 if o.id == selected else 0.0) for o in q.options},
                ),
                source="rules",
            )
        if isinstance(q, ScoreQuestion):
            value = float(raw) if raw is not None else q.min
            return DecisionSurfaceResult(
                kind="score",
                signal=ScoreSignal(id=q.id, value=value),
                source="rules",
            )
        if isinstance(q, NoulQuestion):
            p = float(raw) if raw is not None else 0.0
            return DecisionSurfaceResult(
                kind="noul",
                signal=NoulSignal(id=q.id, p_true=p),
                source="rules",
            )
        raise TypeError(f"unsupported question type {type(q)!r}")


def reject_invalid_choice(
    signal: ChoiceSignal, allowed: Sequence[str]
) -> DecisionSurfaceResult:
    rejected = signal.selected not in set(allowed)
    return DecisionSurfaceResult(
        kind="choice",
        signal=signal,
        source="inference",
        rejected=rejected,
        reject_reason="choice_not_allowed" if rejected else None,
    )
