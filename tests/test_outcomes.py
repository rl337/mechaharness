"""Inference outcome type smoke tests."""

from __future__ import annotations

from mechaharness.core.outcomes import Completion, Generation
from mechaharness.core.types import ChatMessage, CompletionResponse, Role
from mechaharness.inference.judge import Judgement, JudgeResult, JudgeProvenance, JudgeUsage
from mechaharness.policy import JudgementFacts, JudgementPolicy, JudgementThreshold, decide
from mechaharness.inference.judge import NoulSignal


def test_completion_aliases_completion_response() -> None:
    assert Completion is CompletionResponse
    msg = ChatMessage(role=Role.ASSISTANT, content="ok")
    out: Completion = CompletionResponse(message=msg)
    assert out.message.content == "ok"


def test_generation_placeholder() -> None:
    gen = Generation(prompt_id="p1", paths=["/tmp/out.png"], content_type="image/png", bytes=12)
    assert gen.kind == "generation"
    assert gen.paths == ["/tmp/out.png"]


def test_judgement_alias_and_policy() -> None:
    assert JudgeResult is Judgement
    judgement = Judgement(
        request_id="r1",
        state_hash="sha256:x",
        question_set_version="v1",
        answers=[NoulSignal(id="e", p_true=0.9)],
        provenance=JudgeProvenance(provider="fixture", model_revision="v1"),
        usage=JudgeUsage(latency_ms=1.0),
    )
    verdict = decide(
        JudgementFacts(action="x"),
        judgement,
        JudgementPolicy(
            version="v1",
            thresholds=[JudgementThreshold(signal_id="e", allow_above=0.5)],
        ),
    )
    assert verdict.kind == "ALLOW"
