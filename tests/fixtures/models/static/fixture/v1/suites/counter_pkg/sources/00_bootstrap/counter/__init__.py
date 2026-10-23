"""Tiny Counter library — bootstrap."""

from __future__ import annotations


class Counter:
    def __init__(self, value: int = 0) -> None:
        self.value = int(value)
