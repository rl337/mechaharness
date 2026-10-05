"""Versioned environment snapshots plus deltas for context projection.

WalkingLabs Codex design prefers environment deltas over repeating full
snapshots
(https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/codex/).

::

    >>> from mechaharness.environment_delta import (
    ...     EnvironmentSnapshot, apply_deltas, emit_delta,
    ... )
    >>> base = EnvironmentSnapshot(version=1, data={"python": "3.11", "cwd": "/app"})
    >>> newer = EnvironmentSnapshot(version=2, data={"python": "3.11", "cwd": "/tmp"})
    >>> delta = emit_delta(base, newer)
    >>> apply_deltas(base, [delta]).data["cwd"]
    '/tmp'
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EnvironmentSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    data: dict[str, Any] = Field(default_factory=dict)


class EnvironmentDelta(BaseModel):
    model_config = ConfigDict(extra="allow")

    from_version: int
    to_version: int
    set_fields: dict[str, Any] = Field(default_factory=dict)
    removed_fields: list[str] = Field(default_factory=list)


def emit_delta(before: EnvironmentSnapshot, after: EnvironmentSnapshot) -> EnvironmentDelta:
    set_fields = {
        k: v for k, v in after.data.items() if before.data.get(k) != v
    }
    removed = [k for k in before.data if k not in after.data]
    return EnvironmentDelta(
        from_version=before.version,
        to_version=after.version,
        set_fields=set_fields,
        removed_fields=removed,
    )


def apply_deltas(
    base: EnvironmentSnapshot, deltas: list[EnvironmentDelta]
) -> EnvironmentSnapshot:
    data = dict(base.data)
    version = base.version
    for delta in deltas:
        for key in delta.removed_fields:
            data.pop(key, None)
        data.update(delta.set_fields)
        version = delta.to_version
    return EnvironmentSnapshot(version=version, data=data)
