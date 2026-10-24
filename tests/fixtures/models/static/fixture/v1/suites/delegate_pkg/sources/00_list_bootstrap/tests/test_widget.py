from widget import Widget


def test_starts_at_zero() -> None:
    assert Widget().value == 0
