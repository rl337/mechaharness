from counter import Counter


def test_starts_at_zero() -> None:
    assert Counter().value == 0
