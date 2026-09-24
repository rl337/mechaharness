"""Bounded auto-research (EXP) tests."""

from __future__ import annotations

from mechaharness.research import EvalProtocol, ResearchLab, run_bounded_search


def test_research_rejects_cheaper_worse() -> None:
    lab = ResearchLab(
        EvalProtocol(task_split="frozen-v1"),
        baseline_metric=0.8,
    )
    results = run_bounded_search(
        lab,
        [
            ("use tiny model", {"model": "tiny"}, 0.5, True),
            ("better prompt", {"prompt": "v2"}, 0.85, True),
        ],
    )
    assert results[0].status.value == "rejected"
    assert results[1].status.value == "accepted"
    lab.promote(results[1])
    assert lab.promoted is results[1]
