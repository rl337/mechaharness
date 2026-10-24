"""CLI math calculator — number literals."""
from __future__ import annotations

import sys


def evaluate(expr: str) -> float:
    text = expr.strip()
    if not text:
        raise ValueError("empty expression")
    return float(text)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: calc.py <expression>", file=sys.stderr)
        return 2
    try:
        print(evaluate(args[0]))
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
