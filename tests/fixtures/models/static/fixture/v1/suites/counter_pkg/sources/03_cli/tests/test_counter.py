from pathlib import Path

from counter import Counter


def test_starts_at_zero() -> None:
    assert Counter().value == 0


def test_inc_dec() -> None:
    c = Counter()
    assert c.inc() == 1
    assert c.dec() == 0


def test_save_load(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    c = Counter()
    c.inc(5)
    c.save(path)
    assert Counter.load(path).value == 5
