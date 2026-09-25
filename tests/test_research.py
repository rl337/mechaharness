"""Bounded auto-research (EXP) tests."""

from __future__ import annotations

import pytest

from mechaharness.research import (
    ATK_SEARCH_DIMENSIONS,
    EvalProtocol,
    ResearchLab,
    run_bounded_search,
)


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


def test_atk_report_and_evaluator_protection() -> None:
    lab = ResearchLab(EvalProtocol(task_split="atk-v1"), baseline_metric=0.9)
    assert "decision_backend" in ATK_SEARCH_DIMENSIONS
    with pytest.raises(RuntimeError, match="authoritative evaluator"):
        lab.propose("hack", {"authoritative_evaluator": "mine"})
    cheap = lab.propose("cheap", {"model": "tiny"})
    lab.evaluate(cheap, metric=0.2, whole_task_cost=0.01)
    good = lab.propose("solid", {"verification_strategy": "tests"})
    lab.evaluate(good, metric=0.95, ablations={"no_ctx": 0.9})
    lab.promote(good)
    report = lab.report()
    assert cheap.id in report.rejected_cheap_failures
    assert report.promoted_id == good.id
    lab.rollback()
    assert lab.promoted is None
