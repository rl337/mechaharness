# Durable graph generators

| Surface | Value |
|---------|-------|
| Package | `mechaharness.durable_graph_generator` |
| Host kit | `host_kit.host_durable_graph_generator`, `durable_generator_host`, `durable_generator_script` |
| Config | `MechaHarnessConfig.get_durable_graph_generator` / `get_generator_run_store` / `get_generator_controller_auth` |
| Stability | evolving (in-process + stdio MCP; CLI/TUI still gap) |
| Normative | [Durable graph generators](../requirements/durable-graph-generators.md) |

## Role

Primary **host-facing** execution façade for long-running, judgment-bearing
graphs. Drivers (frontier MCP client, human CLI/TUI, `ScriptedDriver`) advance
a durable run through ordered `GraphYield` envelopes. `GraphExecutor` remains
the internal walker; MCP is a transport adapter, not core.

One-shot / fire-and-forget harness loops (`RunRequest` / `run()`, direct
`GraphExecutor.run`) remain valid for short work. Prefer the generator when the
run may yield guidance, outlive a process, or be driven from an external
session.

## Public types

| Type | Purpose |
|------|---------|
| `DurableGraphGenerator` | `start` / `resume` / `inspect` / `cancel` / `list_recipes` |
| `DurableInstrumentor` / `DurableScript` | Verb-led host session script (`start` / `answer` / `inspect` / `rebuild`) |
| `GraphYield` | Ordered immutable yield (`kind`, `sequence`, `request_id`, …) |
| `GuidanceRequest` / `GuidanceResponse` | Typed advice exchange |
| `RunInspection` | Diagnostics without advancing |
| `ScriptedDriver` | Strict offline replay |
| `GeneratorRunStore` | Continuation persistence (`InMemoryGeneratorRunStore`, checkpoint-backed) |
| `GeneratorControllerAuth` / `LeaseControllerAuth` | Controller ownership |

### Yield kinds

`advice_requested`, `completed`, `failed`, `cancelled`, optional `progress` /
`running`.

## Quick start

```python
from mechaharness.host_kit import host_durable_graph_generator
from mechaharness.durable_graph_generator import GuidanceResponse, ScriptedDriver

gen = host_durable_graph_generator()
status = gen.start(
    "verify_repair",
    {
        "guidance": [
            {
                "question": "Which repair path?",
                "choices": [
                    {"id": "retry", "label": "Retry"},
                    {"id": "escalate", "label": "Escalate"},
                ],
            }
        ]
    },
    controller_id="host",
)
while status.kind not in {"completed", "failed", "cancelled"}:
    if status.kind == "advice_requested":
        status = gen.resume(
            status.run_id,
            GuidanceResponse(request_id=status.request_id or "", choice_id="retry"),
            expected_sequence=status.sequence,
            controller_id="host",
            idempotency_key=f"{status.run_id}:{status.sequence}",
        )
    else:
        status = gen.resume(
            status.run_id,
            expected_sequence=status.sequence,
            controller_id="host",
        )
```

Offline regression:

```python
driver = ScriptedDriver(gen)
driver.run(
    "verify_repair",
    {"guidance": [{"request_id": "r1", "question": "Q?", "choices": [{"id": "a", "label": "A"}]}]},
    responses=[{"request_id": "r1", "choice_id": "a"}],
    expected_kinds=["advice_requested", "completed"],
)
```

## Intended HTTP / CLI / MCP mapping

| Client | Mapping |
|--------|---------|
| In-process / stories | `DurableInstrumentor` + verb-led script over `DurableGraphGenerator` |
| OpenAPI / HTTP | Long-run façade methods mirror DG-01 ops (planned; not a second architecture) |
| CLI / TUI | Same instrumentor / soft-point seam (curses optional) — gap |
| MCP stdio | `python -m mechaharness.mcp_graph_driver` — tools `generator_start` / `generator_resume` / `generator_inspect` / `generator_cancel` / `generator_list_recipes`. Stdio framing is newline-delimited JSON (Cursor); Content-Length is still accepted. |
| Story scenarios | `scenario.yaml` under kind `durable_generator` — readable step script + per-step hard `expect` (tests only) |

Soft points are the UI seam: story fixtures and a future CLI/TUI bind the same
guidance answers via `answer` steps; `DurableGraphGenerator` owns suspension/resume.
The instrumentor is host-facing (not a test harness); pytest only loads YAML and
asserts observations.

### MCP example (doctest)

The module docstring on `mechaharness.mcp_graph_driver` is the blessed end-to-end
example (start → `advice_requested` → file-store restart → resume → `completed`,
plus a Cursor-style NDJSON handshake). Run it with::

    pytest --doctest-modules src/mechaharness/mcp_graph_driver.py -q

### Local Cursor wiring

Project-local `.cursor/mcp.json` (gitignored; absolute paths are machine-local)::

    {
      "mcpServers": {
        "mechaharness-generator": {
          "command": "/ABS/PATH/to/.venv/bin/python",
          "args": ["-m", "mechaharness.mcp_graph_driver"],
          "cwd": "/ABS/PATH/to/mechaharness",
          "env": {
            "MECHA_GENERATOR_STORE": "/ABS/PATH/to/.mechaharness/generator-runs.json",
            "MECHA_GENERATOR_CONTROLLER": "cursor-agent",
            "PYTHONPATH": "/ABS/PATH/to/src",
            "PYTHONUNBUFFERED": "1"
          }
        }
      }
    }

## Related

- [Architecture](../architecture.md) — structural map
- [Transactional durable resume](../requirements/transactional-durable-resume.md)
- [Approval interrupts](../inspiration/walkinglabs-harness-engineering-inspiration.md) — distinct from advice
- [Self-revising recipes](../inspiration/self-revising-recipe-evolution.md) — which recipe is active
