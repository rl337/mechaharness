"""Provider-neutral judge types and validation (JDG-*).

Adapters (System One, fixtures) map wire JSON onto these types. Models produce
signals only — policy authority lives in ``mechaharness.judgement_policy``.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.core.exceptions import InferenceError, MechaHarnessError

JUDGE_SCHEMA_VERSION = "1"
ADAPTER_VERSION = "1"
PROB_TOLERANCE = 0.05


class JudgeError(MechaHarnessError):
    """Judge request or response failed validation / transport."""


class QuestionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    instructions: str


class NoulQuestion(QuestionBase):
    kind: Literal["noul"] = "noul"
    criteria: dict[str, str] = Field(
        default_factory=lambda: {"true": "true", "false": "false"}
    )


class ChoiceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""


class ChoiceQuestion(QuestionBase):
    kind: Literal["choice"] = "choice"
    options: list[ChoiceOption]


class ScoreAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    description: str = ""


class ScoreQuestion(QuestionBase):
    kind: Literal["score"] = "score"
    min: float = 0.0
    max: float = 1.0
    anchors: list[ScoreAnchor] = Field(default_factory=list)


Question = Union[NoulQuestion, ChoiceQuestion, ScoreQuestion]


class SignalBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str


class NoulSignal(SignalBase):
    kind: Literal["noul"] = "noul"
    p_true: float = Field(alias="pTrue")

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ChoiceSignal(SignalBase):
    kind: Literal["choice"] = "choice"
    selected: str
    probabilities: dict[str, float] = Field(default_factory=dict)


class ScoreSignal(SignalBase):
    kind: Literal["score"] = "score"
    value: float
    distribution: list[dict[str, float]] | None = None


Signal = Union[NoulSignal, ChoiceSignal, ScoreSignal]


class JudgeErrorItem(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    question_id: str | None = Field(default=None, alias="questionId")
    code: Literal["timeout", "unavailable", "invalid", "unsupported"]


class JudgeProvenance(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    provider: str
    model_revision: str = Field(alias="modelRevision")
    adapter_version: str = Field(default=ADAPTER_VERSION, alias="adapterVersion")
    inference_mode: str = Field(default="batch", alias="inferenceMode")
    calibration_version: str | None = Field(default=None, alias="calibrationVersion")
    calibration_status: Literal["uncalibrated", "validated"] = Field(
        default="uncalibrated", alias="calibrationStatus"
    )


class JudgeUsage(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    latency_ms: float = Field(alias="latencyMs")
    input_tokens: int | None = Field(default=None, alias="inputTokens")
    output_tokens: int | None = Field(default=None, alias="outputTokens")
    cost_usd: float | None = Field(default=None, alias="costUsd")
    physical_calls: int = Field(default=1, alias="physicalCalls")


class Judgement(BaseModel):
    """Decide-lane outcome: validated signals for a question set (JDG-*).

    Distinct from generative ``Completion`` and media ``Generation``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = Field(default=JUDGE_SCHEMA_VERSION, alias="schemaVersion")
    request_id: str = Field(alias="requestId")
    state_hash: str = Field(alias="stateHash")
    question_set_version: str = Field(alias="questionSetVersion")
    answers: list[Signal] = Field(default_factory=list)
    errors: list[JudgeErrorItem] = Field(default_factory=list)
    provenance: JudgeProvenance
    usage: JudgeUsage
    raw: dict[str, Any] = Field(default_factory=dict)


# Backward-compatible alias (REQUIREMENTS / older call sites).
JudgeResult = Judgement


class JudgeRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    state: Any
    state_hash: str = Field(alias="stateHash")
    questions: list[Question]
    question_set_version: str = Field(alias="questionSetVersion")
    deadline_ms: int = Field(default=30_000, alias="deadlineMs")
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="traceId")

    @model_validator(mode="after")
    def _unique_ids(self) -> JudgeRequest:
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question ids must be unique")
        return self


def hash_state(state: Any) -> str:
    """Stable sha256 hash of JSON-serialized state."""
    payload = json.dumps(state, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _finite(value: float, *, label: str) -> float:
    if not math.isfinite(value):
        raise JudgeError(f"{label} must be finite, got {value!r}")
    return value


def validate_signal(question: Question, signal: Signal) -> Signal:
    """Validate one answer against its question (JDG-02)."""
    if signal.id != question.id:
        raise JudgeError(f"signal id {signal.id!r} != question id {question.id!r}")
    if signal.kind != question.kind:
        raise JudgeError(
            f"signal kind {signal.kind!r} != question kind {question.kind!r} "
            f"for {question.id!r}"
        )
    if isinstance(question, NoulQuestion) and isinstance(signal, NoulSignal):
        p = _finite(signal.p_true, label=f"{question.id}.p_true")
        if p < 0.0 or p > 1.0:
            raise JudgeError(f"{question.id}.p_true out of range: {p}")
        return signal
    if isinstance(question, ChoiceQuestion) and isinstance(signal, ChoiceSignal):
        option_ids = {opt.id for opt in question.options}
        if signal.selected not in option_ids:
            raise JudgeError(
                f"{question.id}.selected {signal.selected!r} not in options "
                f"{sorted(option_ids)}"
            )
        probs = {
            k: _finite(v, label=f"{question.id}.probabilities[{k}]")
            for k, v in signal.probabilities.items()
        }
        if probs:
            total = sum(probs.values())
            if abs(total - 1.0) > PROB_TOLERANCE:
                raise JudgeError(
                    f"{question.id} probabilities sum to {total}, "
                    f"tolerance {PROB_TOLERANCE}"
                )
            for key in probs:
                if key not in option_ids:
                    raise JudgeError(
                        f"{question.id} probability key {key!r} not in options"
                    )
        return signal.model_copy(update={"probabilities": probs})
    if isinstance(question, ScoreQuestion) and isinstance(signal, ScoreSignal):
        value = _finite(signal.value, label=f"{question.id}.value")
        if value < question.min or value > question.max:
            raise JudgeError(
                f"{question.id}.value {value} outside [{question.min}, {question.max}]"
            )
        return signal
    raise JudgeError(f"unsupported question/signal pair for {question.id!r}")


def validate_judge_result(
    request: JudgeRequest,
    *,
    answers: Sequence[Signal],
    errors: Sequence[JudgeErrorItem] | None = None,
    provenance: JudgeProvenance,
    usage: JudgeUsage,
    raw: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> Judgement:
    """Build a validated ``Judgement`` (missing answers → error, not zero risk)."""
    by_id = {a.id: a for a in answers}
    if len(by_id) != len(answers):
        raise JudgeError("duplicate answer ids")
    validated: list[Signal] = []
    err_list = list(errors or [])
    answered = set()
    for question in request.questions:
        signal = by_id.get(question.id)
        if signal is None:
            err_list.append(
                JudgeErrorItem(question_id=question.id, code="invalid")
            )
            continue
        try:
            validated.append(validate_signal(question, signal))
            answered.add(question.id)
        except JudgeError:
            err_list.append(
                JudgeErrorItem(question_id=question.id, code="invalid")
            )
    for extra_id in set(by_id) - {q.id for q in request.questions}:
        err_list.append(JudgeErrorItem(question_id=extra_id, code="unsupported"))
    return Judgement(
        request_id=request_id or request.trace_id,
        state_hash=request.state_hash,
        question_set_version=request.question_set_version,
        answers=validated,
        errors=err_list,
        provenance=provenance,
        usage=usage,
        raw=dict(raw or {}),
    )


class JudgeProvider(ABC):
    """Backend that answers a judge request."""

    @abstractmethod
    async def judge(self, request: JudgeRequest) -> Judgement:
        """Return a validated ``Judgement`` for ``request``."""


class FixtureJudgeProvider(JudgeProvider):
    """Deterministic fixture provider for contract tests."""

    def __init__(
        self,
        answers: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        model_revision: str = "fixture-v1",
        fail_ids: Sequence[str] | None = None,
        latency_ms: float = 1.0,
    ) -> None:
        self._answers = dict(answers or {})
        self._model_revision = model_revision
        self._fail_ids = set(fail_ids or [])
        self._latency_ms = latency_ms

    async def judge(self, request: JudgeRequest) -> Judgement:
        started = time.perf_counter()
        signals: list[Signal] = []
        errors: list[JudgeErrorItem] = []
        for question in request.questions:
            if question.id in self._fail_ids:
                errors.append(JudgeErrorItem(question_id=question.id, code="unavailable"))
                continue
            payload = self._answers.get(question.id)
            if payload is None:
                payload = self._default_answer(question)
            signals.append(self._to_signal(question, payload))
        elapsed = (time.perf_counter() - started) * 1000.0
        return validate_judge_result(
            request,
            answers=signals,
            errors=errors,
            provenance=JudgeProvenance(
                provider="fixture",
                model_revision=self._model_revision,
                calibration_status="uncalibrated",
            ),
            usage=JudgeUsage(
                latency_ms=self._latency_ms or elapsed,
                physical_calls=1,
            ),
            raw={"answers": self._answers},
        )

    def _default_answer(self, question: Question) -> dict[str, Any]:
        if isinstance(question, NoulQuestion):
            return {"p_true": 0.5}
        if isinstance(question, ChoiceQuestion):
            first = question.options[0].id
            probs = {opt.id: (1.0 if opt.id == first else 0.0) for opt in question.options}
            return {"selected": first, "probabilities": probs}
        mid = (question.min + question.max) / 2.0
        return {"value": mid}

    def _to_signal(self, question: Question, payload: Mapping[str, Any]) -> Signal:
        if isinstance(question, NoulQuestion):
            return NoulSignal(id=question.id, p_true=float(payload["p_true"]))
        if isinstance(question, ChoiceQuestion):
            return ChoiceSignal(
                id=question.id,
                selected=str(payload["selected"]),
                probabilities={
                    str(k): float(v) for k, v in dict(payload.get("probabilities") or {}).items()
                },
            )
        return ScoreSignal(
            id=question.id,
            value=float(payload["value"]),
            distribution=payload.get("distribution"),
        )


async def judge(
    request: JudgeRequest | Mapping[str, Any],
    *,
    provider: JudgeProvider,
) -> Judgement:
    """Run a validated judge call through ``provider`` (JDG-01/02/03)."""
    req = (
        request
        if isinstance(request, JudgeRequest)
        else JudgeRequest.model_validate(request)
    )
    try:
        return await provider.judge(req)
    except JudgeError:
        raise
    except InferenceError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise JudgeError(str(exc)) from exc
