from mechaharness.eval_evidence import Claim
from mechaharness.evaluator import CallableEvaluator, evaluate_claims


def test_evaluate_claims() -> None:
    ev = CallableEvaluator(
        lambda subject: [
            Claim(
                id="ok",
                statement="ok",
                status="pass" if subject.get("ok") else "fail",
            )
        ],
        evaluator_id="t",
        held_out=True,
    )
    result = evaluate_claims(ev, {"ok": True})
    assert result.passed and result.held_out
