# Durable graph generators requirements map

Maps themes from
[durable-graph-generators-inversion-of-control.md](./durable-graph-generators-inversion-of-control.md)
and normative
[durable-graph-generators.md](../requirements/durable-graph-generators.md)
(`DG-*` / `R-IOC-*`) to modules and user stories.

**Coverage:** *story* means a persona story exercises an integrated library path;
*partial* means helpers ship but host/adapter integration remains open;
*gap* means the product contract is not shipped.

**Ownership:** MechaHarness owns the generator contract, yields, continuation
persistence, controller auth, ScriptedDriver, events, and node components.
Hosts own frontier session context, artistic policy, MCP process lifecycle, and
CLI presentation. MCP is an adapter, not core.

| ID | Topic | Modules | Library | Story | Gaps |
|----|-------|---------|---------|-------|------|
| R-IOC-GENERATOR / DG-01 | Durable ordered yields | `durable_graph_generator.py`, `host_kit.py`, `di.py` | story | `fangore_insp_durable_graph_generator` | — |
| R-IOC-GUIDANCE / DG-03 | Typed guidance suspension | `GuidanceRequest`, soft point `guidance`, node component `guidance_request` | story | `fangore_insp_graph_guidance_yield` | Full GraphExecutor mid-walk suspension hooks deepen post-M1 |
| R-IOC-SESSION / DG-04 | Caller-session resume | `DurableGraphGenerator.start` / `resume` | story | `fangore_insp_driver_session_resume` | — |
| R-IOC-REPLAY / DG-07 | ScriptedDriver strict fixtures | `ScriptedDriver` | story | `taloneth_insp_scripted_driver_replay` | — |
| R-IOC-RESUME / DG-08 | Survive restart | `GeneratorRunStore`, `CheckpointStore` | story | `fangore_insp_guidance_survive_restart` | SQLite-backed run store matrix expands with DR crash windows |
| R-IOC-IDEMPOTENT / DG-09 | Sequence + idempotency | `resume(..., idempotency_key=)` | story | `fangore_insp_guidance_resume_idempotent` | — |
| R-IOC-AUTH / DG-10 | Controller lease; advice ≠ approval | `LeaseControllerAuth`, `ApprovalInterrupt` cite | story | `fangore_insp_guidance_controller_auth` | Explicit lease transfer (M5) |
| R-IOC-BUDGET / DG-11 | Local work vs guidance frequency | `GeneratorCostCounters` / `inspect().cost` | partial | `nubble_insp_guidance_cost_budget` | Deep cost accountant integration later |
| R-IOC-MCP / DG-05 | Stdio MCP adapter | `mcp_graph_driver.py`, `FileGeneratorRunStore` | unit/doctest | `tests/test_mcp_graph_driver.py`, module doctest | — |
| R-IOC-DRIVERS / DG-06 | Shared agent/CLI/script contract | `durable_generator_host`, `ScriptedDriver`, MCP | partial | durable `scenario.yaml` stories + MCP doctest | CLI/TUI clients (soft-point UI; M4) |
| R-IOC-OFFLINE / DG-07 | No live models required | ScriptedDriver + generator stories | story | covered by replay / generator stories | — |

## Related inspirations

- [Self-revising recipe evolution](./self-revising-recipe-evolution.md) — which registered recipe is active (offline evolution)
- [Transactional durable resume](../requirements/transactional-durable-resume.md) — checkpoint / effect recovery seam
- Approval interrupt / sparse advisor stories — cite, do not collapse into advice yields
