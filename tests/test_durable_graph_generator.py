"""Unit coverage for DurableGraphGenerator (M1 in-process contract)."""

from __future__ import annotations

import pytest
from pyiv.time import PythonDateTimeService

from mechaharness.core.events import InMemoryEventLog
from mechaharness.durable_graph_generator import (
    DurableGraphGenerator,
    GraphYieldPublished,
    GuidanceRequest,
    GuidanceResponse,
    InMemoryGeneratorRunStore,
    ScriptedDriver,
)
from mechaharness.graph_templates import GraphTemplateRegistry, VerifyRepairTemplate


def _generator(
    store: InMemoryGeneratorRunStore | None = None,
) -> tuple[DurableGraphGenerator, InMemoryGeneratorRunStore, InMemoryEventLog]:
    registry = GraphTemplateRegistry([VerifyRepairTemplate()])
    runs = store or InMemoryGeneratorRunStore()
    log = InMemoryEventLog()
    gen = DurableGraphGenerator(
        registry=registry,
        run_store=runs,
        event_log=log,
        datetime_service=PythonDateTimeService(),
    )
    return gen, runs, log


def test_complete_on_start_without_guidance() -> None:
    gen, _, log = _generator()
    y = gen.start("verify_repair", {"goal": "ok"}, controller_id="c1")
    assert y.kind == "completed"
    assert y.sequence == 1
    assert y.recipe_id == "verify_repair"
    published = log.query(types=[GraphYieldPublished])
    assert len(published) == 1


def test_guidance_yield_resume_complete() -> None:
    gen, _, _ = _generator()
    y = gen.start(
        "verify_repair",
        {
            "guidance": [
                {
                    "question": "How should exhaustion affect the sword?",
                    "choices": [
                        {"id": "slow", "label": "Slower"},
                        {"id": "precise", "label": "Precise"},
                    ],
                    "recommendation": "precise",
                    "requested_authority": "artistic_direction",
                }
            ]
        },
        controller_id="c1",
        run_id="folk-1",
    )
    assert y.kind == "advice_requested"
    assert y.request_id
    assert y.sequence == 1
    done = gen.resume(
        "folk-1",
        GuidanceResponse(request_id=y.request_id or "", choice_id="precise"),
        expected_sequence=1,
        controller_id="c1",
        idempotency_key="k1",
    )
    assert done.kind == "completed"
    assert done.sequence == 2
    # Idempotent repeat
    again = gen.resume(
        "folk-1",
        GuidanceResponse(request_id=y.request_id or "", choice_id="precise"),
        expected_sequence=1,
        controller_id="c1",
        idempotency_key="k1",
    )
    assert again.kind == "completed"
    assert again.sequence == 2


def test_stale_sequence_and_wrong_controller_rejected() -> None:
    gen, _, _ = _generator()
    y = gen.start(
        "verify_repair",
        {"guidance": [{"question": "Q?", "choices": [{"id": "a", "label": "A"}]}]},
        controller_id="owner",
        run_id="r1",
    )
    with pytest.raises(ValueError, match="stale sequence"):
        gen.resume(
            "r1",
            GuidanceResponse(request_id=y.request_id or "", choice_id="a"),
            expected_sequence=99,
            controller_id="owner",
        )
    with pytest.raises(PermissionError):
        gen.resume(
            "r1",
            GuidanceResponse(request_id=y.request_id or "", choice_id="a"),
            expected_sequence=1,
            controller_id="intruder",
        )


def test_final_approval_authority_rejected_on_ordinary_guidance() -> None:
    gen, _, _ = _generator()
    y = gen.start(
        "verify_repair",
        {
            "guidance": [
                {
                    "question": "Ship?",
                    "requested_authority": "final_approval",
                    "choices": [{"id": "yes", "label": "Yes"}],
                }
            ]
        },
        controller_id="c1",
        run_id="r-appr",
    )
    with pytest.raises(PermissionError, match="ApprovalInterrupt"):
        gen.resume(
            "r-appr",
            GuidanceResponse(request_id=y.request_id or "", choice_id="yes"),
            expected_sequence=1,
            controller_id="c1",
        )


def test_restart_rehydrates_pending_guidance() -> None:
    store = InMemoryGeneratorRunStore()
    gen1, _, _ = _generator(store)
    y = gen1.start(
        "verify_repair",
        {"guidance": [{"question": "Pending?", "choices": [{"id": "ok", "label": "OK"}]}]},
        controller_id="c1",
        run_id="persist-1",
    )
    assert y.kind == "advice_requested"
    # Fresh generator, same store (process restart).
    gen2, _, _ = _generator(store)
    insp = gen2.inspect("persist-1")
    assert insp.phase == "guidance_required"
    assert insp.pending_request is not None
    assert insp.pending_request.question == "Pending?"
    assert insp.pending_request.request_id == y.request_id


def test_scripted_driver_strict_unexpected_advice() -> None:
    gen, _, _ = _generator()
    driver = ScriptedDriver(gen)
    with pytest.raises(AssertionError, match="unexpected advice"):
        driver.run(
            "verify_repair",
            {
                "guidance": [
                    GuidanceRequest(
                        question="Unexpected",
                        choices=[],
                    )
                ]
            },
            responses=[],
            strict_unexpected_advice=True,
        )


def test_scripted_driver_happy_path() -> None:
    gen, _, _ = _generator()
    driver = ScriptedDriver(gen)
    yields = driver.run(
        "verify_repair",
        {
            "guidance": [
                {
                    "request_id": "req-1",
                    "question": "Choose",
                    "choices": [{"id": "a", "label": "A"}],
                }
            ]
        },
        responses=[GuidanceResponse(request_id="req-1", choice_id="a")],
        expected_kinds=["advice_requested", "completed"],
    )
    assert [y.kind for y in yields] == ["advice_requested", "completed"]


def test_list_recipes_and_cancel() -> None:
    gen, _, _ = _generator()
    recipes = gen.list_recipes()
    assert any(r.recipe_id == "verify_repair" for r in recipes)
    y = gen.start(
        "verify_repair",
        {"guidance": [{"question": "Q", "choices": [{"id": "a", "label": "A"}]}]},
        controller_id="c1",
        run_id="cancel-me",
    )
    cancelled = gen.cancel("cancel-me", controller_id="c1", expected_sequence=y.sequence)
    assert cancelled.kind == "cancelled"


def test_host_kit_factory() -> None:
    from mechaharness.host_kit import host_durable_graph_generator

    gen = host_durable_graph_generator()
    assert "verify_repair" in {r.recipe_id for r in gen.list_recipes()}
    y = gen.start("verify_repair", {}, controller_id="host")
    assert y.kind == "completed"
