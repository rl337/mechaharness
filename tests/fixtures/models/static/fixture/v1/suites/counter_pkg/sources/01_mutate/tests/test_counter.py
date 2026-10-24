from counter import Counter


def test_starts_at_zero() -> None:
    assert Counter().value == 0


def test_inc_dec() -> None:
    c = Counter()
    assert c.inc() == 1
    assert c.inc(2) == 3
    assert c.dec() == 2
