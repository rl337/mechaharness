# Host integration requirements

## Motivation

MechaHarness is a **library**. Downstream products (consoles, warehouses,
multi-tenant runtimes) must get full capability by subclassing and composing —
never by forking this repo or patching closed enums, maps, or `match` lists.

This page is the normative contract for **host application code** and for
coding agents working in those repos. Customer-facing Cursor skills that
encode the same rules live under [`agent-skills/`](../../agent-skills/)
(install guide: [Agent skills for your project](../guides/agent-skills.md)).

## Ownership boundary

| MechaHarness owns | Host owns |
|-------------------|-----------|
| Emit contract, correlator names, typed event families | Warehouse DDL, ETL, BI, console UI |
| `MechaHarnessConfig` hooks and default injectables | Durable denial DB, campaign orchestration, tenant policy |
| Agentic Recipe catalog + soft-point substrate | Soft-point bindings, effectful runners, node kinds |
| `host_apis` / `host_kit` discovery surfaces | Product opinion on when to promote / escalate |
| Open identity wire form (`ns:name`) | Host namespaces and grant vocabularies |

## Requirements

### HOST-01: Config-first wiring

Hosts MUST subclass `MechaHarnessConfig` (or use `factory.run` / OpenAPI, which
still constructs a Config) and obtain graph executors, gates, and policies via
injection or `host_kit` helpers. Hosts MUST NOT grow a parallel string registry
or service locator for harness families / inference backends.

### HOST-02: Blessed imports

When discovering inspiration-era safety and recipe surfaces, hosts SHOULD
prefer `from mechaharness.host_apis import …` over mining leaf modules.
Maintainer leaf paths remain valid; `host_apis` is the catalog.

### HOST-03: Promotion path

Product hosts MUST use `promote_recipe` (or `registry.promote_with_final_test`)
when a catalog pointer move needs a held-out gate and/or host opinion.
Ungated `registry.promote` is advanced / migration only. When
`EvolutionCampaignHooks` are bound, hosts SHOULD pass them to `promote_recipe`
so `on_promotion` is observed.

### HOST-04: Open identity

Hosts MUST add new event types, grants, and similar concepts as classes /
namespaced strings that round-trip without a central MechaHarness registry
edit. Hosts MUST NOT require a PR to this library solely to register a host
name.

### HOST-05: Observability export

Hosts that load `EventLog` into a warehouse MUST treat OBS correlators
(`graph_id`, `recipe_id` / `recipe_version`, `authorization_epoch`, nest
`parent_run_id`, …) as foreign keys — see
[Event analytics schema](./event-analytics-schema.md). Hosts MUST NOT strip
those keys at ingest to “save space”; filter in queries instead. Payloads MUST
NOT carry secrets.

### HOST-06: Durability stays with the host

Default `InMemoryDenialStore` and no-op campaign hooks are NOT restart-durable
product storage. Hosts that need multi-tenant denial equivalence, campaign
ledgers, or warehouse tables MUST bind their own implementations via Config
hooks.

### HOST-07: Consumer agent skills stay current

When a host vendors or copies files from `agent-skills/`, it SHOULD re-fetch
from GitHub `main` after MechaHarness releases that change public host APIs,
correlators, or promote guidance. Stale copies are a host ops concern;
upstream keeps `agent-skills/` accurate in the same change as API shifts.

## See also

- [Agent skills for your project](../guides/agent-skills.md)
- [Dependency injection](../guides/dependency-injection.md)
- [Inspiration primitives](../reference/inspiration-primitives.md)
- [Event analytics schema](./event-analytics-schema.md)
