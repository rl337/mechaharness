from widget import Widget


def test_starts_at_zero() -> None:
    assert Widget().value == 0


def test_inc() -> None:
    w = Widget()
    assert w.inc() == 1
    assert w.inc(2) == 3


def test_double() -> None:
    w = Widget(3)
    assert w.double() == 6
    assert w.value == 6
