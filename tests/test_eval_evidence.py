from mechaharness.eval_evidence import Claim, Evidence, all_passed, compose_claims


def test_compose_claims() -> None:
    claims = [
        Claim(id="a", statement="a", status="pass"),
        Claim(id="b", statement="b", status="fail"),
        Claim(id="c", statement="c", status="unknown"),
    ]
    assert compose_claims(claims) == {"pass": 1, "fail": 1, "unknown": 1}
    assert not all_passed(claims)
    assert Evidence(ref="e1", kind="trace").ref == "e1"
