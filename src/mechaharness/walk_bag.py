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

Checkpoint durability uses :meth:`WalkBag.serialize` / :meth:`deserialize`
(deep, JSON-safe + tagged ``FileArtifact``). :meth:`snapshot` remains a
shallow view for in-process observations that do not cross a process boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

_FILE_ARTIFACT_TAG = "FileArtifact"
_TYPE_KEY = "__walk_bag_type__"


class WalkBagRegister:
    """Well-known bag keys (register file)."""

    IN = "in"
    OUT = "out"
    ACC = "acc"
    CTX = "ctx"
    ASK = "ask"
    ANS = "ans"
    ERR = "err"


class WalkBagSerializeError(ValueError):
    """Raised when a bag value cannot be JSON-checkpointed."""


class WalkBagPathError(KeyError):
    """Raised when a register-rooted path is missing or ill-typed."""


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


def _split_path(path: str) -> list[str]:
    parts = [p for p in path.split(".") if p]
    if not parts or path != ".".join(parts):
        raise WalkBagPathError(f"invalid walk bag path {path!r}")
    return parts


def _encode(value: Any) -> Any:
    if isinstance(value, FileArtifact):
        payload = value.model_dump(mode="json")
        return {_TYPE_KEY: _FILE_ARTIFACT_TAG, **payload}
    if isinstance(value, BaseModel):
        raise WalkBagSerializeError(
            f"unsupported bag value type {type(value).__name__}; "
            "use FileArtifact or JSON-safe data"
        )
    if isinstance(value, Mapping):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_encode(v) for v in value]
    if isinstance(value, tuple):
        raise WalkBagSerializeError("tuple is not a supported walk bag value")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise WalkBagSerializeError(
        f"unsupported bag value type {type(value).__name__}"
    )


def _decode(value: Any) -> Any:
    if isinstance(value, Mapping):
        tagged = value.get(_TYPE_KEY)
        if tagged == _FILE_ARTIFACT_TAG:
            data = {k: v for k, v in value.items() if k != _TYPE_KEY}
            return FileArtifact.model_validate(data)
        if tagged is not None:
            raise WalkBagSerializeError(f"unknown walk bag type tag {tagged!r}")
        return {str(k): _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise WalkBagSerializeError(
        f"unsupported serialized bag value type {type(value).__name__}"
    )


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

    def path_get(self, path: str) -> Any:
        """Read a register-rooted dotted path (missing → :class:`WalkBagPathError`)."""
        parts = _split_path(path)
        current: Any = self._data
        for i, part in enumerate(parts):
            if not isinstance(current, Mapping) or part not in current:
                raise WalkBagPathError(
                    f"walk bag missing path {path!r} at {'.'.join(parts[: i + 1])!r}"
                )
            current = current[part]
        return current

    def path_require(self, path: str) -> Any:
        return self.path_get(path)

    def path_put(self, path: str, value: Any) -> None:
        """Write ``value`` at a register-rooted path, creating intermediate dicts."""
        parts = _split_path(path)
        if len(parts) == 1:
            self._data[parts[0]] = value
            return
        cursor: MutableMapping[str, Any] = self._data
        for part in parts[:-1]:
            existing = cursor.get(part)
            if existing is None:
                nested: dict[str, Any] = {}
                cursor[part] = nested
                cursor = nested
                continue
            if not isinstance(existing, MutableMapping):
                raise WalkBagPathError(
                    f"walk bag path {path!r} parent {part!r} is not a mapping"
                )
            cursor = existing
        cursor[parts[-1]] = value

    def snapshot(self) -> dict[str, Any]:
        """Shallow copy for in-process observations (not checkpoint-safe)."""
        return dict(self._data)

    def serialize(self) -> dict[str, Any]:
        """Deep, JSON-safe checkpoint payload (rejects unsupported values)."""
        return {str(k): _encode(v) for k, v in self._data.items()}

    @classmethod
    def deserialize(cls, payload: Mapping[str, Any] | None) -> WalkBag:
        """Rebuild a bag from :meth:`serialize` output (independent copy)."""
        if not payload:
            return cls()
        return cls({str(k): _decode(v) for k, v in payload.items()})

    def deep_snapshot(self) -> WalkBag:
        """Independent deep copy via serialize/deserialize round-trip."""
        return self.deserialize(self.serialize())

    def staged_writes(self) -> WalkBagWriteBatch:
        """Collect validated puts, then apply atomically on :meth:`WalkBagWriteBatch.commit`."""
        return WalkBagWriteBatch(self)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)


class WalkBagWriteBatch:
    """Pending path writes applied together after validation."""

    def __init__(self, bag: WalkBag) -> None:
        self._bag = bag
        self._pending: list[tuple[str, Any]] = []

    def put(self, path: str, value: Any) -> WalkBagWriteBatch:
        # Validate path shape and encode-ability before mutating the live bag.
        _split_path(path)
        _encode(value)
        self._pending.append((path, value))
        return self

    def commit(self) -> None:
        # Re-validate encode + path parents against a scratch copy, then apply.
        scratch = self._bag.deep_snapshot()
        for path, value in self._pending:
            scratch.path_put(path, value)
        scratch.serialize()  # fail closed if any value became unserializable
        for path, value in self._pending:
            self._bag.path_put(path, value)
        self._pending.clear()


__all__ = [
    "FileArtifact",
    "WalkBag",
    "WalkBagPathError",
    "WalkBagRegister",
    "WalkBagSerializeError",
    "WalkBagWriteBatch",
]
