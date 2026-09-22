# Access control

Deny-by-default tool grants. Module: `mechaharness.core.access`.
Stability: evolving.

## Surface

| Item | Value |
|------|-------|
| Module | `mechaharness.core.access` |
| Event | `core:access_check` |
| Stability | evolving |

## Grants

`Grant` is a class hierarchy, not an enum. Intermediate classes set
`namespace`; leaves set `name`. The wire form is `namespace:name`. Unknown
namespaced keys round-trip; bare names (`fs.write`) are rejected.

Built-in `CoreGrant` leaves (`FsRead`, `FsWrite`, `NetHttp`, `MediaImage`,
`MediaVideo`, `MediaAudio`) are conveniences. Hosts add types without editing
this package:

```python
from mechaharness.core.access import Grant

class Widget(Grant):
    namespace = "acme"
    name = "widget"

assert Widget.key() == "acme:widget"
```

`Grant.parse("core:fs.write")` returns the registered class. Unregistered keys
still store on `AccessPolicy.grants`; `parse` raises `KeyError` for those.

## Policy and checks

`AccessPolicy` is a grant list. A tool may run only when every grant it
declares is held (`set(required) <= set(granted)`). Tools that declare no
grants always pass.

`InMemoryAccessControl` holds that list, records each check, and emits
`core:access_check` when `agent_id` and `run_id` are set.

Bind grants through Config:

```python
from mechaharness.core.access import FsWrite
from mechaharness.di import MechaHarnessConfig

class AppConfig(MechaHarnessConfig):
    def get_grants(self):
        return [FsWrite]
```

Or pass `access=InMemoryAccessControl(grants=[FsWrite], event_log=log)` into
`AbstractHarness`. Denied tools return an error `ToolResult` and are not
priced.

## Tools

`Tool` / `ToolRegistry.tool()` accept `grants=` (classes or `namespace:name`
strings) and `ability=` (`Ability`, default `simple`). Demo `echo` / `add`
tools declare none.
