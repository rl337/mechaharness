"""Static + domain tests for instruction_todo_plan."""

from __future__ import annotations

from pyiv.time import PythonDateTimeService

from mechaharness.core.events import InMemoryEventLog
from mechaharness.durable_graph_generator import (
    DurableGraphGenerator,
    GeneratorRunRecord,
    GuidanceResponse,
    InMemoryGeneratorRunStore,
)
from mechaharness.generator_local_work import GeneratorLocalWork
from mechaharness.graph_templates import (
    GraphTemplateParams,
    InstructionTodoPlanTemplate,
    default_graph_templates,
)
from mechaharness.instruction_plan import (
    build_instruction_plan,
    classify_mode,
    detect_conflicts,
)
from mechaharness.node_component import node_components_for


def test_instruction_todo_plan_in_catalog() -> None:
    assert "instruction_todo_plan" in default_graph_templates().names()


def test_instruction_todo_plan_topology() -> None:
    graph = InstructionTodoPlanTemplate().instantiate(
        GraphTemplateParams(goal="ship helpers", inputs={"max_items": 3})
    )
    assert graph.template_name == "instruction_todo_plan"
    for nid in (
        "classify",
        "refine_plan",
        "pre_accept",
        "work_item",
        "item_accept",
        "post_accept",
        "complete",
    ):
        assert nid in graph.nodes
    assert graph.nodes["work_item"].repeating is True
    comps = node_components_for(graph)
    assert comps
    kinds = {c.kind for c in comps}
    assert "soft_point" in kinds or "stop_contract" in kinds


def test_classify_oneshot_vs_list() -> None:
    assert classify_mode({"instruction_mode": "oneshot"}) == "oneshot"
    assert classify_mode({"instructions": ["a", "b"]}) == "list"
    assert classify_mode({"instructions": "do the thing"}) == "oneshot"
    assert (
        classify_mode(
            {"instructions": "1. add helper\n2. add test\n3. update docs"}
        )
        == "list"
    )


def test_detect_conflicts() -> None:
    conflicts = detect_conflicts(["delete the cache", "keep the cache"])
    assert conflicts


def test_build_plan_requests_list_refinement() -> None:
    built = build_instruction_plan(
        {
            "instruction_mode": "list",
            "instructions": ["delete foo", "keep foo"],
            "post_acceptance": ["consistent"],
        }
    )
    assert built.plan is None
    assert built.guidance
    assert built.guidance[0].context_version == "list_refinement"


def test_build_plan_after_list_refinement_restart() -> None:
    history = [
        {
            "request": {
                "context_version": "list_refinement",
                "question": "conflicts",
            },
            "response": {
                "choice_id": "revise",
                "text": "1. remove foo\n2. add bar",
            },
        }
    ]
    built = build_instruction_plan(
        {
            "instruction_mode": "list",
            "instructions": ["delete foo", "keep foo"],
        },
        guidance_history=history,
    )
    assert built.plan is not None
    assert built.plan.mode == "list"
    assert len(built.plan.items) == 2
    assert "remove foo" in built.plan.items[0].instruction


class _RefinementLocalWork(GeneratorLocalWork):
    """First call asks for scope refinement; second completes."""

    def run(self, record: GeneratorRunRecord) -> dict:
        if not any(
            (h.get("request") or {}).get("context_version") == "scope_refinement"
            for h in record.guidance_history
            if isinstance(h, dict)
        ):
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
                        "recommendation": "oneshot",
                    }
                ],
            }
        return {"result": "ok", "restarted": True}


def test_plan_classify_local_work_oneshot_and_conflict() -> None:
    from mechaharness.generator_local_work import PlanClassifyLocalWork

    work = PlanClassifyLocalWork()
    record = GeneratorRunRecord(
        run_id="pc-1",
        recipe_id="instruction_todo_plan",
        graph_id="g",
        controller_id="unit",
        inputs={"goal": "do thing"},
    )
    ok = work.run(record)
    assert ok["result"] == "ok"
    assert ok["mode"] == "oneshot"
    assert ok["plan"]["items"][0]["instruction"] == "do thing"

    conflict = GeneratorRunRecord(
        run_id="pc-2",
        recipe_id="instruction_todo_plan",
        graph_id="g",
        controller_id="unit",
        inputs={"instructions": ["delete foo", "keep foo"]},
    )
    ask = work.run(conflict)
    assert ask["result"] == "needs_guidance"
    assert ask["request_guidance"][0]["context_version"] == "list_refinement"


def test_generator_request_guidance_then_restart() -> None:
    store = InMemoryGeneratorRunStore()
    gen = DurableGraphGenerator(
        registry=default_graph_templates(),
        run_store=store,
        event_log=InMemoryEventLog(),
        datetime_service=PythonDateTimeService(),
        local_work=_RefinementLocalWork(),
    )
    y1 = gen.start(
        "instruction_todo_plan",
        {"goal": "ambiguous task", "instruction_mode": "oneshot"},
        controller_id="unit",
        run_id="plan-refine-1",
    )
    assert y1.kind == "advice_requested"
    assert y1.payload.get("context_version") == "scope_refinement" or (
        y1.summary and "oneshot" in y1.summary.lower()
    )
    y2 = gen.resume(
        y1.run_id,
        GuidanceResponse(request_id=y1.request_id or "", choice_id="oneshot"),
        expected_sequence=y1.sequence,
        controller_id="unit",
        idempotency_key="plan-refine-1:1",
    )
    assert y2.kind == "completed"
    assert y2.payload.get("restarted") is True


class _DecomposeLocalWork(GeneratorLocalWork):
    """First call yields decompose; after answer, builds list plan and completes."""

    def run(self, record: GeneratorRunRecord) -> dict:
        from mechaharness.instruction_plan import (
            build_instruction_plan,
            decompose_guidance_ask,
            guidance_asks_to_payloads,
            has_answered_decompose,
        )

        if not has_answered_decompose(list(record.guidance_history)):
            ask = decompose_guidance_ask(
                ["verify boom A", "verify boom B"],
                ["fix A", "fix B"],
            )
            return {
                "result": "needs_guidance",
                "request_guidance": guidance_asks_to_payloads([ask]),
                "plan_phase": "decompose",
            }
        built = build_instruction_plan(
            dict(record.inputs or {}),
            guidance_history=list(record.guidance_history),
        )
        assert built.plan is not None
        assert built.plan.mode == "list"
        assert len(built.plan.items) == 2
        return {
            "result": "ok",
            "restarted": True,
            "mode": built.plan.mode,
            "plan": {
                "items": [{"instruction": i.instruction} for i in built.plan.items]
            },
        }


def test_generator_decompose_guidance_then_restart() -> None:
    store = InMemoryGeneratorRunStore()
    gen = DurableGraphGenerator(
        registry=default_graph_templates(),
        run_store=store,
        event_log=InMemoryEventLog(),
        datetime_service=PythonDateTimeService(),
        local_work=_DecomposeLocalWork(),
    )
    y1 = gen.start(
        "instruction_todo_plan",
        {"goal": "oneshot that will escalate"},
        controller_id="unit",
        run_id="plan-decomp-1",
    )
    assert y1.kind == "advice_requested"
    assert y1.payload.get("context_version") == "decompose"
    assert y1.payload.get("proposed_instructions") == ["fix A", "fix B"]
    y2 = gen.resume(
        y1.run_id,
        GuidanceResponse(
            request_id=y1.request_id or "",
            choice_id="accept_proposed",
        ),
        expected_sequence=y1.sequence,
        controller_id="unit",
        idempotency_key="plan-decomp-1:1",
    )
    assert y2.kind == "completed"
    assert y2.payload.get("restarted") is True
    assert y2.payload.get("mode") == "list"
    items = (y2.payload.get("plan") or {}).get("items") or []
    assert [i["instruction"] for i in items] == ["fix A", "fix B"]
