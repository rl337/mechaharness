"""Tools so a parent agent can query sub-agent event logs."""

from __future__ import annotations

import json

from mechaharness.core.events import EventLog, event_type_key
from mechaharness.tools.base import ToolRegistry

DEFAULT_EVENT_LIMIT = 50


def install_subagent_tools(
    tools: ToolRegistry,
    event_log: EventLog,
    agent_id: str,
    *,
    limit: int = DEFAULT_EVENT_LIMIT,
) -> None:
    """Register ``list_subagents`` and ``get_subagent_events`` if missing."""
    parent_id = agent_id

    if "list_subagents" not in tools:

        @tools.tool(
            description="List sub-agents spawned by this agent.",
            parameters={"type": "object", "properties": {}},
        )
        def list_subagents() -> str:
            children = event_log.agents(parent_id=parent_id)
            return json.dumps(
                [
                    {
                        "agent_id": ref.agent_id,
                        "parent_agent_id": ref.parent_agent_id,
                        "label": ref.label,
                    }
                    for ref in children
                ]
            )

    if "get_subagent_events" not in tools:

        @tools.tool(
            description=(
                "Return structured events for a sub-agent. "
                "Only descendants of this agent are visible."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "event_type": {"type": "string"},
                    "descendants": {"type": "boolean"},
                },
                "required": ["agent_id"],
            },
        )
        def get_subagent_events(
            agent_id: str,
            event_type: str = "",
            descendants: bool = False,
        ) -> str:
            return _query_child_events(
                event_log,
                parent_id=parent_id,
                target_id=agent_id,
                event_type=event_type,
                descendants=descendants,
                limit=limit,
            )


def _descendant_ids(event_log: EventLog, parent_id: str) -> set[str]:
    return {
        event.agent_id
        for event in event_log.query(agent_id=parent_id, descendants=True)
        if event.agent_id != parent_id
    }


def _query_child_events(
    event_log: EventLog,
    *,
    parent_id: str,
    target_id: str,
    event_type: str,
    descendants: bool,
    limit: int,
) -> str:
    if target_id not in _descendant_ids(event_log, parent_id):
        return json.dumps({"error": f"agent {target_id!r} is not a sub-agent"})
    types = None
    if event_type:
        try:
            types = [event_type_key(event_type)]
        except ValueError:
            return json.dumps({"error": f"invalid event type {event_type!r}"})
    events = event_log.query(agent_id=target_id, descendants=descendants, types=types)
    dumped = [event.model_dump(mode="json") for event in events[:limit]]
    return json.dumps(
        {"count": len(dumped), "truncated": len(events) > limit, "events": dumped}
    )
