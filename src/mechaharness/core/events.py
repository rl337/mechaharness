"""Queryable structured event log.

A harness is an agent with a finite run. Parent agents share one ``EventLog``
with children and query it (including via tools). This module has no harness
or injector imports.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, ClassVar, Union

from pydantic import BaseModel, Field, field_validator

LOGGER_NAME = "mechaharness.events"


class EventType:
    """Namespaced event identity.

    Subclass to add types. The wire form is ``namespace:name`` (for example
    ``core:agent_start``). Intermediate classes set ``namespace``; leaves set
    ``name``.
    """

    namespace: ClassVar[str] = ""
    name: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            return
        if not cls.namespace:
            raise TypeError(f"{cls.__name__} must set namespace (via a base class)")
        if ":" in cls.namespace or ":" in cls.name:
            raise ValueError("namespace and name must not contain ':'")
        key = cls.key()
        existing = _EVENT_TYPES.get(key)
        if existing is not None and existing is not cls:
            raise ValueError(f"duplicate event type {key!r} ({existing.__name__})")
        _EVENT_TYPES[key] = cls

    @classmethod
    def key(cls) -> str:
        if not cls.namespace or not cls.name:
            raise TypeError(f"{cls.__name__} is not a concrete event type")
        return f"{cls.namespace}:{cls.name}"

    @classmethod
    def parse(cls, value: str) -> type[EventType]:
        """Return the class registered for ``namespace:name``."""
        _require_namespaced(value)
        try:
            return _EVENT_TYPES[value]
        except KeyError as exc:
            raise KeyError(f"unknown event type {value!r}") from exc


_EVENT_TYPES: dict[str, type[EventType]] = {}
EventTypeRef = Union[str, type[EventType]]


class CoreEvent(EventType):
    """Built-in MechaHarness events (``core:*``)."""

    namespace = "core"


class AgentStart(CoreEvent):
    name = "agent_start"


class AgentEnd(CoreEvent):
    name = "agent_end"


class RunStart(CoreEvent):
    name = "run_start"


class RunEnd(CoreEvent):
    name = "run_end"


class TurnStart(CoreEvent):
    name = "turn_start"


class Inference(CoreEvent):
    name = "inference"


class ToolCall(CoreEvent):
    name = "tool_call"


class ToolResult(CoreEvent):
    name = "tool_result"


class MaxTurns(CoreEvent):
    name = "max_turns"


class Cost(CoreEvent):
    name = "cost"


class AccessCheck(CoreEvent):
    name = "access_check"


def event_type_key(value: object) -> str:
    """Normalize a class or ``namespace:name`` string to the wire key."""
    if isinstance(value, str):
        _require_namespaced(value)
        return value
    if isinstance(value, type) and issubclass(value, EventType):
        return value.key()
    raise TypeError(f"event type must be EventType subclass or str, got {value!r}")


def _require_namespaced(value: str) -> None:
    namespace, sep, name = value.partition(":")
    if not sep or not namespace or not name:
        raise ValueError(f"event type must be namespace:name, got {value!r}")
    if ":" in name:
        raise ValueError(f"event type must be namespace:name, got {value!r}")


class Event(BaseModel):
    """One structured log record."""

    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: str
    agent_id: str
    run_id: str
    parent_agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, value: object) -> str:
        return event_type_key(value)


class AgentRef(BaseModel):
    """An agent observed in the log."""

    agent_id: str
    parent_agent_id: str | None = None
    first_ts: datetime
    last_ts: datetime
    label: str | None = None


class EventLog(ABC):
    """Write and query structured agent events."""

    @abstractmethod
    def emit(self, event: Event) -> None:
        """Append one event."""

    @abstractmethod
    def query(
        self,
        *,
        agent_id: str | None = None,
        run_id: str | None = None,
        descendants: bool = False,
        types: Sequence[EventTypeRef] | None = None,
    ) -> list[Event]:
        """Return matching events in emit order."""

    @abstractmethod
    def agents(self, *, parent_id: str | None = None) -> list[AgentRef]:
        """Agents seen in the log. ``parent_id`` limits to direct children."""


class InMemoryEventLog(EventLog):
    """List-backed store with agent / run / parent indexes."""

    def __init__(self) -> None:
        self._events: list[Event] = []

    def emit(self, event: Event) -> None:
        self._events.append(event)

    def query(
        self,
        *,
        agent_id: str | None = None,
        run_id: str | None = None,
        descendants: bool = False,
        types: Sequence[EventTypeRef] | None = None,
    ) -> list[Event]:
        type_set = {event_type_key(item) for item in types} if types is not None else None
        agent_ids: set[str] | None = None
        if agent_id is not None:
            agent_ids = self._descendant_ids(agent_id) if descendants else {agent_id}
        matched: list[Event] = []
        for event in self._events:
            if agent_ids is not None and event.agent_id not in agent_ids:
                continue
            if run_id is not None and event.run_id != run_id:
                continue
            if type_set is not None and event.type not in type_set:
                continue
            matched.append(event)
        return matched

    def agents(self, *, parent_id: str | None = None) -> list[AgentRef]:
        by_id: dict[str, AgentRef] = {}
        for event in self._events:
            existing = by_id.get(event.agent_id)
            label = _label_from_payload(event.payload)
            if existing is None:
                by_id[event.agent_id] = AgentRef(
                    agent_id=event.agent_id,
                    parent_agent_id=event.parent_agent_id,
                    first_ts=event.ts,
                    last_ts=event.ts,
                    label=label,
                )
            else:
                existing.last_ts = event.ts
                if existing.parent_agent_id is None and event.parent_agent_id:
                    existing.parent_agent_id = event.parent_agent_id
                if existing.label is None and label:
                    existing.label = label
        refs = list(by_id.values())
        if parent_id is not None:
            refs = [ref for ref in refs if ref.parent_agent_id == parent_id]
        return refs

    def _descendant_ids(self, root: str) -> set[str]:
        children: dict[str, set[str]] = {}
        for event in self._events:
            if event.parent_agent_id:
                children.setdefault(event.parent_agent_id, set()).add(event.agent_id)
        found = {root}
        stack = [root]
        while stack:
            current = stack.pop()
            for child in children.get(current, ()):
                if child not in found:
                    found.add(child)
                    stack.append(child)
        return found


class LoggingEventLog(EventLog):
    """Write adapter: one JSON line per event on ``mechaharness.events``.

    Not a store: ``query`` / ``agents`` return empty lists.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(LOGGER_NAME)

    def emit(self, event: Event) -> None:
        line = json.dumps(event.model_dump(mode="json"), default=str, sort_keys=True)
        self._logger.info(line)

    def query(
        self,
        *,
        agent_id: str | None = None,
        run_id: str | None = None,
        descendants: bool = False,
        types: Sequence[EventTypeRef] | None = None,
    ) -> list[Event]:
        return []

    def agents(self, *, parent_id: str | None = None) -> list[AgentRef]:
        return []


class FanoutEventLog(EventLog):
    """Emit to every log; query / agents use the first non-logging store."""

    def __init__(self, *logs: EventLog) -> None:
        if not logs:
            raise ValueError("FanoutEventLog requires at least one EventLog")
        self._logs = logs
        self._store = next(
            (log for log in logs if not isinstance(log, LoggingEventLog)),
            logs[0],
        )

    def emit(self, event: Event) -> None:
        for log in self._logs:
            log.emit(event)

    def query(
        self,
        *,
        agent_id: str | None = None,
        run_id: str | None = None,
        descendants: bool = False,
        types: Sequence[EventTypeRef] | None = None,
    ) -> list[Event]:
        return self._store.query(
            agent_id=agent_id,
            run_id=run_id,
            descendants=descendants,
            types=types,
        )

    def agents(self, *, parent_id: str | None = None) -> list[AgentRef]:
        return self._store.agents(parent_id=parent_id)


def default_event_log() -> FanoutEventLog:
    """In-memory store plus stdlib logging."""
    return FanoutEventLog(InMemoryEventLog(), LoggingEventLog())


def _label_from_payload(payload: dict[str, Any]) -> str | None:
    for key in ("label", "family", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None
