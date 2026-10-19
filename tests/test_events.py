"""Event log store and logging adapter (no harness wiring)."""

from __future__ import annotations

import json

import pytest
from pyiv.log import MemoryLoggerFactory

from mechaharness.core.events import (
    LOGGER_NAME,
    AgentStart,
    Event,
    EventType,
    EventTypeRef,
    FanoutEventLog,
    Inference,
    InMemoryEventLog,
    LoggingEventLog,
    RunStart,
    ToolCall,
    TurnStart,
)


def _event(
    agent_id: str,
    event_type: EventTypeRef,
    *,
    run_id: str = "run-1",
    parent_agent_id: str | None = None,
    payload: dict[str, str] | None = None,
) -> Event:
    return Event(
        type=event_type,
        agent_id=agent_id,
        run_id=run_id,
        parent_agent_id=parent_agent_id,
        payload=payload or {},
    )


@pytest.mark.parametrize(
    ("case_id", "emit", "query", "expect_agents", "expect_types"),
    [
        (
            "by_agent",
            [
                ("a", TurnStart, "run-1"),
                ("b", TurnStart, "run-1"),
            ],
            {"agent_id": "a"},
            ["a"],
            None,
        ),
        (
            "by_run_and_type",
            [
                ("a", TurnStart, "r1"),
                ("a", Inference, "r1"),
                ("a", TurnStart, "r2"),
            ],
            {"run_id": "r1", "types": [Inference]},
            ["a"],
            [Inference.key()],
        ),
    ],
    ids=["by_agent", "by_run_and_type"],
)
def test_query_filters(
    case_id: str,
    emit: list[tuple[str, object, str]],
    query: dict,
    expect_agents: list[str],
    expect_types: list[str] | None,
) -> None:
    del case_id
    log = InMemoryEventLog()
    for agent_id, event_type, run_id in emit:
        log.emit(_event(agent_id, event_type, run_id=run_id))  # type: ignore[arg-type]
    found = log.query(**query)
    assert [e.agent_id for e in found] == expect_agents
    if expect_types is not None:
        assert [e.type for e in found] == expect_types


def test_descendants_include_parent_and_children() -> None:
    log = InMemoryEventLog()
    log.emit(_event("parent", AgentStart, payload={"family": "tool_loop"}))
    log.emit(
        _event(
            "child",
            AgentStart,
            parent_agent_id="parent",
            payload={"family": "react"},
        )
    )
    log.emit(
        _event(
            "grandchild",
            Inference,
            parent_agent_id="child",
        )
    )
    log.emit(_event("other", TurnStart))
    found = log.query(agent_id="parent", descendants=True)
    ids = {e.agent_id for e in found}
    assert ids == {"parent", "child", "grandchild"}


def test_agents_lists_children_of_parent() -> None:
    log = InMemoryEventLog()
    log.emit(_event("parent", AgentStart, payload={"family": "outer"}))
    log.emit(
        _event(
            "child",
            AgentStart,
            parent_agent_id="parent",
            payload={"family": "inner"},
        )
    )
    children = log.agents(parent_id="parent")
    assert len(children) == 1
    assert children[0].agent_id == "child"
    assert children[0].label == "inner"
    assert children[0].parent_agent_id == "parent"


def test_logging_event_log_writes_json() -> None:
    factory = MemoryLoggerFactory()
    log = LoggingEventLog(logger_factory=factory)
    log.emit(_event("a", RunStart, payload={"prompt_chars": "3"}))
    assert log.query() == []
    assert log.agents() == []
    records = factory.get(LOGGER_NAME).records
    assert len(records) == 1
    body = json.loads(records[0].message)
    assert body["type"] == "core:run_start"
    assert body["agent_id"] == "a"
    assert body["payload"]["prompt_chars"] == "3"


def test_fanout_queries_memory_and_logs() -> None:
    factory = MemoryLoggerFactory()
    memory = InMemoryEventLog()
    log = FanoutEventLog(memory, LoggingEventLog(logger_factory=factory))
    log.emit(_event("a", ToolCall, payload={"name": "add"}))
    found = log.query(agent_id="a")
    assert len(found) == 1
    assert found[0].payload["name"] == "add"
    body = json.loads(factory.get(LOGGER_NAME).records[0].message)
    assert body["type"] == "core:tool_call"


class WidgetDone(EventType):
    namespace = "acme"
    name = "widget"


def test_custom_event_type_subclass() -> None:
    log = InMemoryEventLog()
    log.emit(_event("a", WidgetDone))
    by_class = log.query(types=[WidgetDone])
    by_key = log.query(types=["acme:widget"])
    assert [e.type for e in by_class] == ["acme:widget"]
    assert [e.type for e in by_key] == ["acme:widget"]
    assert WidgetDone.key() == "acme:widget"
    assert EventType.parse("acme:widget") is WidgetDone


def test_unknown_namespaced_string_is_valid() -> None:
    event = Event(type="acme:unregistered", agent_id="a", run_id="run-1")
    assert event.type == "acme:unregistered"
    with pytest.raises(KeyError, match="unknown event type"):
        EventType.parse("acme:unregistered")


def test_bare_event_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="namespace:name"):
        Event(type="run_start", agent_id="a", run_id="run-1")


def _walk_event_types(base: type[EventType] = EventType) -> list[type[EventType]]:
    found: list[type[EventType]] = []
    stack = list(base.__subclasses__())
    while stack:
        cls = stack.pop()
        found.append(cls)
        stack.extend(cls.__subclasses__())
    return found


def test_event_type_namespace_and_name_are_unique() -> None:
    concrete = [cls for cls in _walk_event_types() if cls.namespace and cls.name]
    assert concrete, "expected concrete EventType subclasses"
    by_key: dict[str, str] = {}
    collisions: list[str] = []
    for cls in concrete:
        key = f"{cls.namespace}:{cls.name}"
        other = by_key.get(key)
        if other is not None:
            collisions.append(f"{key} used by {other} and {cls.__name__}")
        else:
            by_key[key] = cls.__name__
        assert cls.key() == key
    assert not collisions, "; ".join(collisions)
