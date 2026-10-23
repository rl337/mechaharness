"""Tiny Counter library — mutate."""

from __future__ import annotations


class Counter:
    def __init__(self, value: int = 0) -> None:
        self.value = int(value)

    def inc(self, n: int = 1) -> int:
        self.value += int(n)
        return self.value

    def dec(self, n: int = 1) -> int:
        self.value -= int(n)
        return self.value
