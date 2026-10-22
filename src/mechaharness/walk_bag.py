"""Walk-scoped register bag for graph / product-surface data flow.

Nodes and thin CLI façades share values through well-known keys (registers),
not by poking sibling ``GraphNode.payload`` dicts. Hosts may add namespaced
keys (``acme:widget``); core runners document which registers they read/write.

Register ABI (minimal set — extend only when a story needs a new job)::

    in   caller params into the next consumer
    out  last producer result (may hold :class:`FileArtifact`)
    acc  accumulator / fold / running verdict
    ctx  sticky walk context (policy id, epoch, …)
    ask  pending human / expectation request
    ans  injected or mocked human answer
    err  last structured failure, if any

``FileArtifact`` is a typed bag value for generated files (disk path or URL).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class WalkBagRegister:
    """Well-known bag keys (register file)."""

    IN = "in"
    OUT = "out"
    ACC = "acc"
    CTX = "ctx"
    ASK = "ask"
    ANS = "ans"
    ERR = "err"


class FileArtifact(BaseModel):
    """Generated file handle published on the walk bag (path or URL)."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    url: str | None = None
    media_type: str | None = None
    producer_node_id: str | None = None
    checksum: str | None = None
    size: int | None = None

    @model_validator(mode="after")
    def _one_location(self) -> FileArtifact:
        has_path = bool(self.path)
        has_url = bool(self.url)
        if has_path == has_url:
            raise ValueError("FileArtifact needs exactly one of path or url")
        return self


class WalkBag:
    """Mutable key→value store for one graph / façade walk."""

    def __init__(self, initial: Mapping[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(initial or {})

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def put(self, key: str, value: Any) -> None:
        self._data[key] = value

    def require(self, key: str) -> Any:
        if key not in self._data:
            raise KeyError(f"walk bag missing key {key!r}; have {sorted(self._data)}")
        return self._data[key]

    def snapshot(self) -> dict[str, Any]:
        """Shallow copy for observations / checkpoints."""
        return dict(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)


__all__ = [
    "FileArtifact",
    "WalkBag",
    "WalkBagRegister",
]
