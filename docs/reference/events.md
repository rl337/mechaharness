# Event log

Queryable structured events for agents. Module: `mechaharness.core.events`.
Stability: evolving. Hosts construct a log and call `emit` / `query` directly.
The harness does not emit on this log yet.

## Surface

| Item | Value |
|------|-------|
| Module | `mechaharness.core.events` |
| Logger | `mechaharness.events` |
| Stability | evolving |

## Envelope

Every record is an `Event`:

| Field | Meaning |
|-------|---------|
| `ts` | UTC timestamp |
| `type` | `EventType` |
| `agent_id` | Agent / harness instance |
| `parent_agent_id` | Optional parent agent |
| `run_id` | One run lifecycle |
| `payload` | JSON object (no API keys) |

`EventType` values: `agent_start`, `agent_end`, `run_start`, `run_end`,
`turn_start`, `inference`, `tool_call`, `tool_result`, `max_turns`, `cost`,
`access_check`. Later harness and policy PRs fill those payloads.

## `EventLog`

```python
class EventLog:
    def emit(self, event: Event) -> None: ...
    def query(
        self,
        *,
        agent_id: str | None = None,
        run_id: str | None = None,
        descendants: bool = False,
        types: Sequence[EventType] | None = None,
    ) -> list[Event]: ...
    def agents(self, *, parent_id: str | None = None) -> list[AgentRef]: ...
```

`query(agent_id=..., descendants=True)` returns that agent plus children
linked by `parent_agent_id`. `agents(parent_id=...)` lists direct children.

## Implementations

- `InMemoryEventLog` — store used for tests and parent queries.
- `LoggingEventLog` — one JSON line per `emit` on logger `mechaharness.events`.
  `query` / `agents` return empty lists (write adapter only).
- `FanoutEventLog(*logs)` — `emit` to every log; `query` / `agents` use the
  first non-logging store.
- `default_event_log()` — fan-out of in-memory + logging.

```python
from mechaharness.core.events import Event, EventType, InMemoryEventLog

log = InMemoryEventLog()
log.emit(
    Event(
        type=EventType.RUN_START,
        agent_id="agent-1",
        run_id="run-1",
        payload={"prompt_chars": 12},
    )
)
assert log.query(agent_id="agent-1")[0].type is EventType.RUN_START
```
