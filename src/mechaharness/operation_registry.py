"""Thin operation registry (INF-01/03) — reject unsupported ops."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from mechaharness.core.exceptions import MechaHarnessError


class UnsupportedOperation(MechaHarnessError):
    """Requested operation is not registered."""


class OperationRegistry:
    """Enough to distinguish chat vs judge vs tool without a global service locator."""

    def __init__(self) -> None:
        self._ops: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, handler: Callable[..., Any]) -> None:
        self._ops[name] = handler

    def supports(self, name: str) -> bool:
        return name in self._ops

    def require(self, name: str) -> Callable[..., Any]:
        try:
            return self._ops[name]
        except KeyError as exc:
            raise UnsupportedOperation(
                f"unsupported operation {name!r}; known: {sorted(self._ops)}"
            ) from exc

    def names(self) -> list[str]:
        return sorted(self._ops)

    def merge(self, other: Mapping[str, Callable[..., Any]]) -> OperationRegistry:
        for name, handler in other.items():
            self.register(name, handler)
        return self


def default_operations() -> OperationRegistry:
    registry = OperationRegistry()
    registry.register("chat", lambda **_: None)
    registry.register("judge", lambda **_: None)
    registry.register("tool", lambda **_: None)
    return registry
