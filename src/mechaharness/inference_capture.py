"""Optional training-grade inference capture (MH-MHRL-04/05/20).

FineEnvs argues on-policy RL may need exact token IDs and generation-time
logprobs, and probes endpoints because providers may omit those fields
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#what-gets-recorded).

MechaHarness exposes a native capture capability with explicit levels;
unsupported fields never silently masquerade as trainable data::

    >>> from mechaharness.inference_capture import (
    ...     EvaluationOnlyCapture, TrainingGradeCapture, CaptureRecord,
    ... )
    >>> eval_cap = EvaluationOnlyCapture()
    >>> eval_cap.supports_level("training_grade")
    False
    >>> train = TrainingGradeCapture()
    >>> rec = train.capture({"token_ids": [1, 2], "logprobs": [-0.1, -0.2]})
    >>> rec.capture_level
    'training_grade'
    >>> rec.unsupported_fields
    []
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CaptureLevel = Literal["none", "evaluation", "training_grade"]


class CaptureRecord(BaseModel):
    """One inference capture with explicit capability honesty."""

    model_config = ConfigDict(extra="allow")

    capture_level: str
    model_revision: str | None = None
    sampling: dict[str, Any] = Field(default_factory=dict)
    token_ids: list[int] | None = None
    logprobs: list[float] | None = None
    request_id: str | None = None
    response_id: str | None = None
    unsupported_fields: list[str] = Field(default_factory=list)
    trainable: bool = False
    detail: dict[str, Any] = Field(default_factory=dict)


class InferenceCapture(ABC):
    """Provider-neutral native capture seam (not a network proxy)."""

    capture_level: CaptureLevel = "none"

    @abstractmethod
    def supports_level(self, level: str) -> bool:
        """Return True when this backend can satisfy ``level``."""

    @abstractmethod
    def capture(self, payload: Mapping[str, Any]) -> CaptureRecord:
        """Capture fields from an in-process completion payload."""

    def assert_compatible(self, required_level: str) -> None:
        if not self.supports_level(required_level):
            raise ValueError(
                f"inference capture level {required_level!r} unsupported "
                f"(have {self.capture_level!r})"
            )


class EvaluationOnlyCapture(InferenceCapture):
    """Default: ordinary telemetry, not training-grade."""

    capture_level: CaptureLevel = "evaluation"

    def supports_level(self, level: str) -> bool:
        return level in {"none", "evaluation"}

    def capture(self, payload: Mapping[str, Any]) -> CaptureRecord:
        unsupported = [
            name
            for name in ("token_ids", "logprobs")
            if name not in payload or payload.get(name) is None
        ]
        return CaptureRecord(
            capture_level=self.capture_level,
            model_revision=payload.get("model_revision"),
            sampling=dict(payload.get("sampling") or {}),
            request_id=payload.get("request_id"),
            response_id=payload.get("response_id"),
            unsupported_fields=unsupported,
            trainable=False,
            detail={"text": payload.get("text")},
        )


class TrainingGradeCapture(InferenceCapture):
    """Captures engine token IDs and behavior-policy logprobs when present."""

    capture_level: CaptureLevel = "training_grade"

    def supports_level(self, level: str) -> bool:
        return level in {"none", "evaluation", "training_grade"}

    def capture(self, payload: Mapping[str, Any]) -> CaptureRecord:
        token_ids = payload.get("token_ids")
        logprobs = payload.get("logprobs")
        unsupported: list[str] = []
        if token_ids is None:
            unsupported.append("token_ids")
        if logprobs is None:
            unsupported.append("logprobs")
        trainable = not unsupported
        return CaptureRecord(
            capture_level=self.capture_level,
            model_revision=payload.get("model_revision"),
            sampling=dict(payload.get("sampling") or {}),
            token_ids=list(token_ids) if token_ids is not None else None,
            logprobs=list(logprobs) if logprobs is not None else None,
            request_id=payload.get("request_id"),
            response_id=payload.get("response_id"),
            unsupported_fields=unsupported,
            trainable=trainable,
        )


def empty_inference_capture() -> InferenceCapture:
    return EvaluationOnlyCapture()
