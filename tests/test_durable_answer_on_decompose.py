"""AnswerBody.on_decompose drains one escalate yield in the durable script path."""

from __future__ import annotations

from mechaharness.durable_generator_script import (
    AnswerBody,
    DurableInstrumentor,
    DurableScript,
    StartBody,
)
from mechaharness.durable_graph_generator import GeneratorRunRecord
from mechaharness.generator_local_work import GeneratorLocalWork
from mechaharness.instruction_plan import (
    decompose_guidance_ask,
    guidance_answers,
    guidance_asks_to_payloads,
    has_answered_decompose,
)


def _has_scope(history: list) -> bool:
    return any(
        a.get("context_version") == "scope_refinement"
        for a in guidance_answers(list(history or []))
    )


class _ScopeThenDecomposeLocalWork(GeneratorLocalWork):
    """scope_refinement → decompose → complete (mirrors coding escalate)."""

    def run(self, record: GeneratorRunRecord) -> dict:
        history = list(record.guidance_history)
        if not _has_scope(history):
            return {
                "result": "needs_guidance",
                "request_guidance": [
                    {
                        "question": "oneshot or list?",
                        "context_version": "scope_refinement",
                        "choices": [
                            {"id": "oneshot", "label": "One shot"},
                            {"id": "list", "label": "List"},
                        ],
                    }
                ],
            }
        if not has_answered_decompose(history):
            ask = decompose_guidance_ask(
                ["verify boom"],
                ["fix boom"],
            )
            return {
                "result": "needs_guidance",
                "request_guidance": guidance_asks_to_payloads([ask]),
                "plan_phase": "decompose",
            }
        return {"result": "ok", "drained": True}


def test_answer_on_decompose_accept_proposed_drains() -> None:
    script = DurableScript(
        graph="instruction_todo_plan",
        controller="unit",
        store="memory",
        steps=[],
    )
    host = DurableInstrumentor(script, local_work=_ScopeThenDecomposeLocalWork())
    started = host.start(StartBody(inputs={"goal": "ship it"}))
    assert started.kind == "advice_requested"
    assert (started.yield_obj.payload or {}).get("context_version") == (
        "scope_refinement"
    )

    finished = host.answer(
        AnswerBody(choose="oneshot", on_decompose="accept_proposed")
    )
    assert finished.kind == "completed"
    assert (finished.yield_obj.payload or {}).get("drained") is True


def test_answer_without_on_decompose_stops_on_escalate() -> None:
    script = DurableScript(
        graph="instruction_todo_plan",
        controller="unit",
        store="memory",
        steps=[],
    )
    host = DurableInstrumentor(script, local_work=_ScopeThenDecomposeLocalWork())
    host.start(StartBody(inputs={"goal": "ship it"}))
    mid = host.answer(AnswerBody(choose="oneshot"))
    assert mid.kind == "advice_requested"
    assert (mid.yield_obj.payload or {}).get("context_version") == "decompose"
