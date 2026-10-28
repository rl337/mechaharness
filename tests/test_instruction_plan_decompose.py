"""Decompose helpers and build_instruction_plan restart after escalate yield."""

from __future__ import annotations

import pytest

from mechaharness.instruction_plan import (
    build_instruction_plan,
    decompose_guidance_ask,
    decompose_instructions_from_failures,
    guidance_asks_to_payloads,
    has_answered_decompose,
)


@pytest.mark.parametrize(
    ("goal", "failures", "expect_count", "first_contains", "also_contains"),
    [
        (
            "Ship calc — do NOT use eval(), exec(), or ast.literal_eval on the user expression.",
            ["a failed", "b failed"],
            1,
            "Extend the existing",
            [
                "Re-establish every previously green",
                "a failed",
                "b failed",
                "do NOT use eval()",
                "Non-negotiables",
                "do not call the eval, exec, or ast.literal_eval functions",
            ],
        ),
        (
            "",
            ["only one"],
            1,
            "Failing checks:",
            ["only one", "Non-negotiables"],
        ),
        ("goal only", [], 1, "goal only", None),
        ("", [], 0, None, None),
    ],
    ids=["multi_consolidated", "single", "empty_failures_goal", "empty"],
)
def test_decompose_instructions_from_failures(
    goal: str,
    failures: list[str],
    expect_count: int,
    first_contains: str | None,
    also_contains: list[str] | None,
) -> None:
    items = decompose_instructions_from_failures(goal, failures)
    assert len(items) == expect_count
    if first_contains is not None and items:
        assert first_contains in items[0]
    for needle in also_contains or []:
        assert needle in items[0]


def test_decompose_guidance_ask_payload_includes_proposed() -> None:
    ask = decompose_guidance_ask(
        ["verify_runs[0] boom", "verify_runs[1] boom"],
        ["fix A", "fix B"],
    )
    assert ask.context_version == "decompose"
    payloads = guidance_asks_to_payloads([ask])
    assert payloads[0]["proposed_instructions"] == ["fix A", "fix B"]
    assert "accept_proposed" in {c["id"] for c in payloads[0]["choices"]}


def test_build_plan_after_decompose_accept_proposed() -> None:
    history = [
        {
            "request": {
                "context_version": "decompose",
                "question": "Break it down",
                "proposed_instructions": ["add * /", "add fn calls"],
            },
            "response": {"choice_id": "accept_proposed"},
        }
    ]
    assert has_answered_decompose(history)
    built = build_instruction_plan(
        {"goal": "original oneshot goal"},
        guidance_history=history,
    )
    assert built.guidance == []
    assert built.plan is not None
    assert built.plan.mode == "list"
    assert built.plan.refined is True
    assert [i.instruction for i in built.plan.items] == ["add * /", "add fn calls"]


def test_auto_decompose_oneshot_skips_drop_keep_conflict_heuristic() -> None:
    """Host escalate brief must not yield list_refinement on preamble wording."""
    from mechaharness.instruction_plan import decompose_instructions_from_failures

    # Consolidated brief cites "Keep …" goals; flag must skip false conflicts
    # when hosts force list mode around the single escalate instruction.
    proposed = decompose_instructions_from_failures(
        "Keep operators green",
        ["verify boom A", "verify boom B"],
    )
    assert len(proposed) == 1
    built = build_instruction_plan(
        {
            "instruction_mode": "list",
            "instructions": proposed,
            "decompose_auto_applied": True,
        }
    )
    assert built.guidance == []
    assert built.plan is not None
    assert built.plan.mode == "list"
    assert len(built.plan.items) == 1


def test_build_plan_after_decompose_revise_text() -> None:
    history = [
        {
            "request": {
                "context_version": "decompose",
                "proposed_instructions": ["old a", "old b"],
            },
            "response": {
                "choice_id": "revise",
                "text": "1. keep literals\n2. add functions\n3. keep grouping",
            },
        }
    ]
    built = build_instruction_plan(
        {"goal": "calc"},
        guidance_history=history,
    )
    assert built.plan is not None
    assert built.plan.mode == "list"
    assert [i.instruction for i in built.plan.items] == [
        "keep literals",
        "add functions",
        "keep grouping",
    ]
