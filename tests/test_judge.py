"""Judge / System One contract tests."""

from __future__ import annotations

import httpx
import pytest

from mechaharness.inference.judge import (
    ChoiceOption,
    ChoiceQuestion,
    ChoiceSignal,
    FixtureJudgeProvider,
    JudgeError,
    JudgeRequest,
    NoulQuestion,
    NoulSignal,
    ScoreAnchor,
    ScoreQuestion,
    ScoreSignal,
    hash_state,
    judge,
    validate_signal,
)
from mechaharness.inference.systemone import SystemOneJudgeProvider


def _mixed_questions() -> list[object]:
    return [
        NoulQuestion(id="escalate", instructions="Needs human?"),
        ChoiceQuestion(
            id="route",
            instructions="Which team?",
            options=[
                ChoiceOption(id="billing", description="Payments"),
                ChoiceOption(id="technical", description="Bugs"),
                ChoiceOption(id="other", description="Else"),
            ],
        ),
        ScoreQuestion(
            id="urgency",
            instructions="How urgent?",
            min=0.0,
            max=2.0,
            anchors=[
                ScoreAnchor(value=0.0, description="not urgent"),
                ScoreAnchor(value=1.0, description="soon"),
                ScoreAnchor(value=2.0, description="blocking"),
            ],
        ),
    ]


@pytest.mark.asyncio
async def test_fixture_judge_mixed_batch() -> None:
    provider = FixtureJudgeProvider(
        {
            "escalate": {"p_true": 0.82},
            "route": {
                "selected": "billing",
                "probabilities": {"billing": 0.91, "technical": 0.05, "other": 0.04},
            },
            "urgency": {"value": 1.7},
        }
    )
    state = {"ticket": "double charge"}
    result = await judge(
        JudgeRequest(
            state=state,
            state_hash=hash_state(state),
            questions=_mixed_questions(),  # type: ignore[arg-type]
            question_set_version="gate-v1",
        ),
        provider=provider,
    )
    assert len(result.answers) == 3
    assert result.errors == []
    by_id = {a.id: a for a in result.answers}
    assert isinstance(by_id["escalate"], NoulSignal)
    assert by_id["escalate"].p_true == 0.82
    assert isinstance(by_id["route"], ChoiceSignal)
    assert by_id["route"].selected == "billing"
    assert isinstance(by_id["urgency"], ScoreSignal)


@pytest.mark.asyncio
async def test_fixture_partial_failure() -> None:
    provider = FixtureJudgeProvider(
        {"escalate": {"p_true": 0.1}},
        fail_ids=["route"],
    )
    result = await judge(
        JudgeRequest(
            state="x",
            state_hash=hash_state("x"),
            questions=_mixed_questions()[:2],  # type: ignore[arg-type]
            question_set_version="v1",
        ),
        provider=provider,
    )
    assert len(result.answers) == 1
    assert any(e.question_id == "route" for e in result.errors)


def test_reject_nan_and_bad_choice() -> None:
    q = NoulQuestion(id="e", instructions="?")
    with pytest.raises(JudgeError, match="finite"):
        validate_signal(q, NoulSignal(id="e", p_true=float("nan")))
    cq = ChoiceQuestion(
        id="r",
        instructions="?",
        options=[ChoiceOption(id="a", description="A")],
    )
    with pytest.raises(JudgeError, match="not in options"):
        validate_signal(cq, ChoiceSignal(id="r", selected="z", probabilities={}))


def test_reject_duplicate_question_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        JudgeRequest(
            state={},
            state_hash="sha256:x",
            questions=[
                NoulQuestion(id="a", instructions="1"),
                NoulQuestion(id="a", instructions="2"),
            ],
            question_set_version="v1",
        )


@pytest.mark.asyncio
async def test_systemone_adapter_maps_wire(httpx_mock: object | None = None) -> None:
    """Transport-level mapping with a mocked HTTP response."""
    payload = {
        "model": "laya",
        "answers": {
            "escalate": {"noul": 0.7},
            "route": {
                "choice": "billing",
                "probabilities": {"billing": 1.0, "technical": 0.0, "other": 0.0},
            },
        },
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/systemone")
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://decide.test") as client:
        provider = SystemOneJudgeProvider(
            base_url="http://decide.test",
            model="laya",
            client=client,
        )
        result = await judge(
            JudgeRequest(
                state="refund",
                state_hash=hash_state("refund"),
                questions=_mixed_questions()[:2],  # type: ignore[arg-type]
                question_set_version="v1",
            ),
            provider=provider,
        )
    assert result.provenance.provider == "systemone"
    assert {a.id for a in result.answers} == {"escalate", "route"}
