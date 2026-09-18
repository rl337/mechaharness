# Event log

Queryable structured events for agents. Module: `mechaharness.core.events`.
Stability: evolving. `AbstractHarness.run()` (including `pass_through`,
`tool_loop`, and `react`) emits lifecycle, inference, tool, access, and cost
records. Hosts can also `emit` / `query` directly.

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
| `type` | Wire key `namespace:name` (for example `core:agent_start`) |
| `agent_id` | Agent / harness instance |
| `parent_agent_id` | Optional parent agent |
| `run_id` | One run lifecycle |
| `payload` | JSON object (no API keys) |

`Event.type` is a string. Pass an `EventType` subclass or a `namespace:name`
string when constructing; both store the same key. Unknown keys are valid as
long as they are namespaced. Bare names (`run_start`) are rejected.

## Event types

`EventType` is a class hierarchy, not an enum. Intermediate classes set
`namespace`; leaves set `name`. Built-in types subclass `CoreEvent`
(`namespace = "core"`):

| Class | Wire key |
|-------|----------|
| `AgentStart` | `core:agent_start` |
| `AgentEnd` | `core:agent_end` |
| `RunStart` | `core:run_start` |
| `RunEnd` | `core:run_end` |
| `TurnStart` | `core:turn_start` |
| `Inference` | `core:inference` |
| `ToolCall` | `core:tool_call` |
| `ToolResult` | `core:tool_result` |
| `MaxTurns` | `core:max_turns` |
| `Cost` | `core:cost` |
| `AccessCheck` | `core:access_check` |

`core:access_check` payload: `tool`, `required`, `granted`, `allowed`. Hosts add types by
subclassing without editing this module:

```python
from mechaharness.core.events import EventType

class WidgetDone(EventType):
    namespace = "acme"
    name = "widget"

assert WidgetDone.key() == "acme:widget"
```

`EventType.parse("core:run_start")` returns the registered class. Unregistered
keys still round-trip on `Event.type`; `parse` raises `KeyError` for those.

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
        types: Sequence[str | type[EventType]] | None = None,
    ) -> list[Event]: ...
    def agents(self, *, parent_id: str | None = None) -> list[AgentRef]: ...
```

`query(agent_id=..., descendants=True)` returns that agent plus children
linked by `parent_agent_id`. `agents(parent_id=...)` lists direct children.
`types=` accepts classes or wire keys.

## Implementations

- `InMemoryEventLog` — store used for tests and parent queries.
- `LoggingEventLog` — one JSON line per `emit` on logger `mechaharness.events`.
  `query` / `agents` return empty lists (write adapter only).
- `FanoutEventLog(*logs)` — `emit` to every log; `query` / `agents` use the
  first non-logging store.
- `default_event_log()` — fan-out of in-memory + logging.

```python
from mechaharness.core.events import Event, InMemoryEventLog, RunStart

log = InMemoryEventLog()
log.emit(
    Event(
        type=RunStart,
        agent_id="agent-1",
        run_id="run-1",
        payload={"prompt_chars": 12},
    )
)
assert log.query(agent_id="agent-1")[0].type == "core:run_start"
```
