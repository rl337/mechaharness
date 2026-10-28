"""Tiny Gadget library — rename from Widget."""

from __future__ import annotations


class Gadget:
    def __init__(self, value: int = 0) -> None:
        self.value = int(value)

    def inc(self, n: int = 1) -> int:
        self.value += int(n)
        return self.value

    def double(self) -> int:
        self.value *= 2
        return self.value
