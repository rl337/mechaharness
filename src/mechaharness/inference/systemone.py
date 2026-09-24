"""System One / Laya-Kev judge adapter (configurable HTTP path)."""

from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from mechaharness.config import Settings
from mechaharness.connection import (
    APIConnectionConfig,
    SimpleHttpConnectionConfig,
)
from mechaharness.core.exceptions import InferenceError
from mechaharness.inference.judge import (
    ADAPTER_VERSION,
    ChoiceQuestion,
    ChoiceSignal,
    JudgeError,
    JudgeErrorItem,
    JudgeProvider,
    JudgeProvenance,
    JudgeRequest,
    Judgement,
    JudgeUsage,
    NoulQuestion,
    NoulSignal,
    Question,
    ScoreQuestion,
    ScoreSignal,
    Signal,
    validate_judge_result,
)


class SystemOneWireModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SystemOneQuestionWire(SystemOneWireModel):
    type: str
    instructions: str = ""
    criteria: Any = None


class SystemOneRequestWire(SystemOneWireModel):
    model: str | None = None
    state: Any
    questions: dict[str, SystemOneQuestionWire]


class SystemOneAnswerWire(SystemOneWireModel):
    choice: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    probs: dict[str, float] | None = None
    score: float | None = None
    distribution: list[float] | None = None
    noul: float | None = None
    p_true: float | None = None
    value: Any = None


class SystemOneResponseWire(SystemOneWireModel):
    model: str | None = None
    answers: dict[str, Any] = Field(default_factory=dict)


def question_to_wire(question: Question) -> SystemOneQuestionWire:
    if isinstance(question, NoulQuestion):
        return SystemOneQuestionWire(
            type="noul",
            instructions=question.instructions,
            criteria=question.criteria,
        )
    if isinstance(question, ChoiceQuestion):
        return SystemOneQuestionWire(
            type="choice",
            instructions=question.instructions,
            criteria={opt.id: opt.description for opt in question.options},
        )
    criteria: list[str]
    if question.anchors:
        criteria = [a.description or str(a.value) for a in question.anchors]
    else:
        criteria = [str(question.min), str(question.max)]
    return SystemOneQuestionWire(
        type="score",
        instructions=question.instructions,
        criteria=criteria,
    )


def _parse_answer(question: Question, raw: Any) -> Signal | None:
    if not isinstance(raw, dict):
        if isinstance(question, NoulQuestion) and isinstance(raw, (int, float)):
            return NoulSignal(id=question.id, p_true=float(raw))
        if isinstance(question, ChoiceQuestion) and isinstance(raw, str):
            return ChoiceSignal(id=question.id, selected=raw, probabilities={})
        if isinstance(question, ScoreQuestion) and isinstance(raw, (int, float)):
            return ScoreSignal(id=question.id, value=float(raw))
        return None
    wire = SystemOneAnswerWire.model_validate(raw)
    if isinstance(question, NoulQuestion):
        p = wire.noul if wire.noul is not None else wire.p_true
        if p is None and isinstance(wire.value, (int, float)):
            p = float(wire.value)
        if p is None:
            return None
        return NoulSignal(id=question.id, p_true=float(p))
    if isinstance(question, ChoiceQuestion):
        selected = wire.choice
        if selected is None and isinstance(wire.value, str):
            selected = wire.value
        if selected is None:
            return None
        probs = wire.probabilities or wire.probs or {}
        return ChoiceSignal(
            id=question.id,
            selected=selected,
            probabilities={str(k): float(v) for k, v in probs.items()},
        )
    score = wire.score
    if score is None and isinstance(wire.value, (int, float)):
        score = float(wire.value)
    if score is None:
        return None
    dist = None
    if wire.distribution is not None and question.anchors:
        dist = [
            {"value": float(question.anchors[i].value), "probability": float(p)}
            for i, p in enumerate(wire.distribution)
            if i < len(question.anchors)
        ]
    return ScoreSignal(id=question.id, value=float(score), distribution=dist)


class SystemOneJudgeProvider(JudgeProvider):
    """HTTP adapter for System One-shaped ``POST`` endpoints (Laya / Kev)."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        connection: APIConnectionConfig | None = None,
        base_url: str | None = None,
        model: str | None = None,
        path: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or Settings()
        if connection is not None:
            self._connection = connection
        else:
            self._connection = SimpleHttpConnectionConfig(
                base_url=base_url if base_url is not None else self._settings.judge_base_url,
                path=path
                if path is not None
                else (self._settings.judge_path or "/v1/systemone"),
                url=self._settings.judge_url,
                api_key=self._settings.judge_api_key or self._settings.api_key,
                model=model if model is not None else self._settings.judge_model,
                timeout=float(
                    timeout
                    if timeout is not None
                    else self._settings.judge_timeout_seconds
                ),
            )
        self._client = client

    async def judge(self, request: JudgeRequest) -> Judgement:
        try:
            url = self._connection.endpoint_url()
        except ValueError as exc:
            raise JudgeError(str(exc)) from exc
        wire_questions = {q.id: question_to_wire(q) for q in request.questions}
        body = SystemOneRequestWire(
            model=self._connection.model_id(),
            state=request.state,
            questions=wire_questions,
        )
        started = time.perf_counter()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._connection.timeout_seconds()
        )
        try:
            response = await client.post(
                url,
                json=body.model_dump(mode="json", exclude_none=True),
                headers=self._connection.headers(),
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise JudgeError("timeout contacting System One") from exc
        except httpx.HTTPError as exc:
            raise InferenceError(f"System One HTTP error: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()
        elapsed = (time.perf_counter() - started) * 1000.0
        parsed = SystemOneResponseWire.model_validate(payload)
        signals: list[Signal] = []
        errors: list[JudgeErrorItem] = []
        for question in request.questions:
            raw_ans = parsed.answers.get(question.id)
            if raw_ans is None:
                errors.append(JudgeErrorItem(question_id=question.id, code="invalid"))
                continue
            signal = _parse_answer(question, raw_ans)
            if signal is None:
                errors.append(JudgeErrorItem(question_id=question.id, code="invalid"))
                continue
            signals.append(signal)
        return validate_judge_result(
            request,
            answers=signals,
            errors=errors,
            provenance=JudgeProvenance(
                provider="systemone",
                model_revision=parsed.model
                or self._connection.model_id()
                or "unknown",
                adapter_version=ADAPTER_VERSION,
                inference_mode="batch",
                calibration_status="uncalibrated",
            ),
            usage=JudgeUsage(latency_ms=elapsed, physical_calls=1),
            raw=payload if isinstance(payload, dict) else {"payload": payload},
            request_id=request.trace_id,
        )
