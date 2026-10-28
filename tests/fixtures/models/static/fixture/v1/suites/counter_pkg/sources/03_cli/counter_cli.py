"""CLI over Counter — show / inc / dec with counter.json."""

from __future__ import annotations

import sys
from pathlib import Path

from counter import Counter

STORE = Path("counter.json")


def _load() -> Counter:
    if STORE.is_file():
        return Counter.load(STORE)
    return Counter()


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"inc", "dec", "show"}:
        print("usage: counter_cli.py <inc|dec|show>", file=sys.stderr)
        return 2
    c = _load()
    cmd = args[0]
    if cmd == "inc":
        c.inc()
    elif cmd == "dec":
        c.dec()
    c.save(STORE)
    print(c.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
