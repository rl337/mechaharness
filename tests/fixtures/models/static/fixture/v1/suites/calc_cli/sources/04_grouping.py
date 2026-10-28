"""CLI math calculator — precedence, ^, and parentheses."""
from __future__ import annotations

import sys


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0

    def skip(self) -> None:
        while self.i < len(self.text) and self.text[self.i].isspace():
            self.i += 1

    def match(self, ch: str) -> bool:
        self.skip()
        if self.i < len(self.text) and self.text[self.i] == ch:
            self.i += 1
            return True
        return False

    def number(self) -> float:
        self.skip()
        start = self.i
        while self.i < len(self.text) and (
            self.text[self.i].isdigit() or self.text[self.i] == "."
        ):
            self.i += 1
        if start == self.i:
            raise ValueError(f"expected number at {start}")
        return float(self.text[start : self.i])

    def primary(self) -> float:
        self.skip()
        if self.match("("):
            value = self.additive()
            if not self.match(")"):
                raise ValueError("expected ')'")
            return value
        return self.number()

    def power(self) -> float:
        base = self.primary()
        if self.match("^"):
            return base ** self.power()
        return base

    def term(self) -> float:
        value = self.power()
        while True:
            if self.match("*"):
                value = value * self.power()
            elif self.match("/"):
                value = value / self.power()
            else:
                break
        return value

    def additive(self) -> float:
        value = self.term()
        while True:
            if self.match("+"):
                value = value + self.term()
            elif self.match("-"):
                value = value - self.term()
            else:
                break
        return value

    def parse(self) -> float:
        value = self.additive()
        self.skip()
        if self.i != len(self.text):
            raise ValueError(f"trailing input at {self.i}")
        return value


def evaluate(expr: str) -> float:
    return _Parser(expr).parse()


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
