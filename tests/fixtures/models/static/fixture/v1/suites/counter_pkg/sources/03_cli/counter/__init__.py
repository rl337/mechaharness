"""Tiny Counter library — persist."""

from __future__ import annotations

import json
from pathlib import Path


class Counter:
    def __init__(self, value: int = 0) -> None:
        self.value = int(value)

    def inc(self, n: int = 1) -> int:
        self.value += int(n)
        return self.value

    def dec(self, n: int = 1) -> int:
        self.value -= int(n)
        return self.value

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({"value": self.value}), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Counter:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(value=int(data["value"]))
