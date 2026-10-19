"""Held-out final-test gate on promotion (MH-SR-07)."""

from __future__ import annotations

import pytest

from mechaharness.evaluator import (
    EvaluatorResult,
    FinalTestGateError,
    require_held_out_final_test,
)
from mechaharness.graph_templates import GraphTemplateRegistry, VerifyRepairTemplate
from mechaharness.research import EvalProtocol, ResearchLab


def _result(*, held_out: bool, passed: bool) -> EvaluatorResult:
    return EvaluatorResult(evaluator_id="e", version="1", held_out=held_out, passed=passed)


_GATE = [
    ("missing", None, "required"),
    ("not_held_out", _result(held_out=False, passed=True), "not held out"),
    ("held_out_failed", _result(held_out=True, passed=False), "did not pass"),
    ("held_out_passed", _result(held_out=True, passed=True), None),
]


@pytest.mark.parametrize(("case_id", "result", "error"), _GATE, ids=[c[0] for c in _GATE])
def test_require_held_out_final_test(case_id: str, result, error: str | None) -> None:
    del case_id
    if error is None:
        require_held_out_final_test(result)
        return
    with pytest.raises(FinalTestGateError, match=error):
        require_held_out_final_test(result)


def _accepted_lab(**protocol: object) -> tuple[ResearchLab, object]:
    lab = ResearchLab(EvalProtocol(task_split="s", **protocol), baseline_metric=0.5)
    candidate = lab.propose("h", {"prompt": "v2"})
    lab.evaluate(candidate, metric=0.9)
    return lab, candidate


@pytest.mark.parametrize(
    "bad", [None, _result(held_out=False, passed=True), _result(held_out=True, passed=False)]
)
def test_research_lab_refuses_promotion_without_a_passing_held_out_result(bad) -> None:
    lab, candidate = _accepted_lab()
    with pytest.raises(FinalTestGateError):
        lab.promote(candidate, final_test=bad)
    assert lab.promoted is None


def test_research_lab_promotes_with_a_passing_held_out_result() -> None:
    lab, candidate = _accepted_lab()
    lab.promote(candidate, final_test=_result(held_out=True, passed=True))
    assert lab.promoted is candidate


def test_unprotected_protocol_skips_the_gate() -> None:
    lab, candidate = _accepted_lab(held_out_protected=False)
    lab.promote(candidate)
    assert lab.promoted is candidate


class _V2(VerifyRepairTemplate):
    version = "2"


def test_registry_final_test_promotion_attaches_the_evidence_and_moves_the_pointer() -> None:
    registry = GraphTemplateRegistry([VerifyRepairTemplate()])
    registry.add_version(_V2(), parent_version="1")
    with pytest.raises(FinalTestGateError):
        registry.promote_with_final_test("verify_repair", "2", final_test=None)
    assert registry.active_version("verify_repair") == "1"
    registry.promote_with_final_test(
        "verify_repair", "2", final_test=_result(held_out=True, passed=True)
    )
    assert registry.active_version("verify_repair") == "2"
    assert registry.evaluations("verify_repair", "2")[0]["gate"] == "final_test"
    with pytest.raises(KeyError):
        registry.promote_with_final_test(
            "verify_repair", "9", final_test=_result(held_out=True, passed=True)
        )
