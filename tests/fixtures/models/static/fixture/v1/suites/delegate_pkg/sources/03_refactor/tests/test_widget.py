from widget import Gadget


def test_starts_at_zero() -> None:
    assert Gadget().value == 0


def test_inc() -> None:
    g = Gadget()
    assert g.inc() == 1
    assert g.inc(2) == 3


def test_double() -> None:
    g = Gadget(3)
    assert g.double() == 6
    assert g.value == 6
