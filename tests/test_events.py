"""Event log store and logging adapter (no harness wiring)."""

from __future__ import annotations

import json
import logging

from mechaharness.core.events import (
    LOGGER_NAME,
    Event,
    EventType,
    FanoutEventLog,
    InMemoryEventLog,
    LoggingEventLog,
)


def _event(
    agent_id: str,
    event_type: EventType,
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


def test_query_filters_by_agent() -> None:
    log = InMemoryEventLog()
    log.emit(_event("a", EventType.TURN_START))
    log.emit(_event("b", EventType.TURN_START))
    found = log.query(agent_id="a")
    assert [e.agent_id for e in found] == ["a"]


def test_query_filters_by_run_and_type() -> None:
    log = InMemoryEventLog()
    log.emit(_event("a", EventType.TURN_START, run_id="r1"))
    log.emit(_event("a", EventType.INFERENCE, run_id="r1"))
    log.emit(_event("a", EventType.TURN_START, run_id="r2"))
    found = log.query(run_id="r1", types=[EventType.INFERENCE])
    assert len(found) == 1
    assert found[0].type == EventType.INFERENCE


def test_descendants_include_parent_and_children() -> None:
    log = InMemoryEventLog()
    log.emit(_event("parent", EventType.AGENT_START, payload={"family": "tool_loop"}))
    log.emit(
        _event(
            "child",
            EventType.AGENT_START,
            parent_agent_id="parent",
            payload={"family": "react"},
        )
    )
    log.emit(
        _event(
            "grandchild",
            EventType.INFERENCE,
            parent_agent_id="child",
        )
    )
    log.emit(_event("other", EventType.TURN_START))
    found = log.query(agent_id="parent", descendants=True)
    ids = {e.agent_id for e in found}
    assert ids == {"parent", "child", "grandchild"}


def test_agents_lists_children_of_parent() -> None:
    log = InMemoryEventLog()
    log.emit(_event("parent", EventType.AGENT_START, payload={"family": "outer"}))
    log.emit(
        _event(
            "child",
            EventType.AGENT_START,
            parent_agent_id="parent",
            payload={"family": "inner"},
        )
    )
    children = log.agents(parent_id="parent")
    assert len(children) == 1
    assert children[0].agent_id == "child"
    assert children[0].label == "inner"
    assert children[0].parent_agent_id == "parent"


def test_logging_event_log_writes_json(caplog) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    log = LoggingEventLog()
    log.emit(_event("a", EventType.RUN_START, payload={"prompt_chars": "3"}))
    assert log.query() == []
    assert log.agents() == []
    assert len(caplog.records) == 1
    body = json.loads(caplog.records[0].message)
    assert body["type"] == "run_start"
    assert body["agent_id"] == "a"
    assert body["payload"]["prompt_chars"] == "3"


def test_fanout_queries_memory_and_logs(caplog) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    memory = InMemoryEventLog()
    log = FanoutEventLog(memory, LoggingEventLog())
    log.emit(_event("a", EventType.TOOL_CALL, payload={"name": "add"}))
    found = log.query(agent_id="a")
    assert len(found) == 1
    assert found[0].payload["name"] == "add"
    assert json.loads(caplog.records[0].message)["type"] == "tool_call"
