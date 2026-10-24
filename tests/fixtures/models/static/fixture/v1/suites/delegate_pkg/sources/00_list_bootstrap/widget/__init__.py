"""Tiny Widget library — list-mode bootstrap."""

from __future__ import annotations


class Widget:
    def __init__(self, value: int = 0) -> None:
        self.value = int(value)
