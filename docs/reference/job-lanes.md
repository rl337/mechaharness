# Job lanes and JobLaneBroker

Lane-scoped run sequences, WalkBags, and authorized observe. Module target:
`mechaharness.job_lane_broker` (shim-deprecate
`mechaharness.isolation.cross_task_isolation.CrossTaskIsolationGuard`).

Stability: evolving (types + Config bind + CLI verbs + JL stories landed).

## Surface

| Item | Value |
|------|-------|
| Types | `JobLane`, `JobLaneBroker`, exposure / grant records |
| DI | Config `get_job_lane_broker()`; inject — no locator |
| CLI | `lane_publish`, `lane_observe`, `lane_grant`, `lane_handoff` |
| Normative | [Job lane broker requirements](../requirements/job-lane-broker.md) |
| Provenance | MH-DOTS-07 (productized as lanes, not intervening-task loops) |

## Mental model

A **JobLane** is a pipeline identity (cron, commit-triggered, or manual). Each
execution is a **run** in that lane’s **run sequence**. The **JobLaneBroker**
holds each run’s WalkBag and answers:

> What were the exposed values (e.g. asset URLs) for lane X — latest, before
> time T, or run_id R — **for caller lane Y**?

Same lane → lineage allowed by default. Other lane → only if the publisher’s
exposure policy and/or standing grants (or a one-shot handoff) permit it.

## WalkBag

Per-run register file (`in` / `out` / `ask` / `ans` / `acc` / `ctx` / `err`).
Typed values include `FileArtifact` (path or url). See
`mechaharness.walk_bag`. The broker owns bags; nodes do not poke another run’s
bag directly.

## Exposure and grants

| Layer | Role |
|-------|------|
| Lane exposure | Publisher declares `meta` and each key: `open`, `deny_all`, or `allow_lanes` |
| Standing grant | Optional broker-level grant from lane A to lane B for keys/meta |
| Handoff | `HandoffRecord` one-shot share of named evidence refs |

`observe` checks publisher policy **and** caller identity (analogous to
`AccessControl` checks).

## Selectors

| Selector | Meaning |
|----------|---------|
| `run_id` | Exact run |
| `latest` | Head of the sequence |
| `before` / `at_or_before` | Last run with timestamp ≤ t |

Trigger kind (time vs commit) does not change the sequence model — only how
runs are appended and optional trigger metadata indexed later.

## Not this page

| Concern | Where |
|---------|--------|
| Subgraph typed I/O / effect scope | `IsolationContract` / `TemplateIOContract` |
| Workspace worktree/container acquire | `WorkspaceIsolationProvider` |
| Tool/fs grants | [Access control](./access.md) |

## Examples (story YAML)

See [JL requirements — YAML surface](../requirements/job-lane-broker.md#user-story-yaml-surface).
