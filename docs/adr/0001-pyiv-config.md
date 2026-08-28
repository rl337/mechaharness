# 0001. pyiv Config instead of string registries

- Status: Accepted
- Date: 2026-08-14

## Context

MechaHarness started with module-level `register_inference` / `register_harness`
dicts and `factory.build_*` helpers. That made CLI flags easy (`--backend openai`)
but fought two goals: using a real injector internally, and letting host apps
inject MechaHarness types into their own graphs.

pyiv `Config` has no `install()` for nested modules. Composition is subclassing.

## Decision

Replace string registries with a template-method `MechaHarnessConfig`:
`get_inference_class()` / `get_harness_class()` run at construction and bind
interfaces. `SettingsConfig` implements those hooks via name maps for OpenAPI
and CLI. `RunRequest` / `factory.run()` remain the non-DI facade; they still
build a Config and inject.

## Consequences

- Extension is subclassing Config (or overriding maps), not decorating factories
- Strategy constructors take `Settings` so pyiv can construct them
- Domain types stay pyiv-free and injectable into host apps
- Callers who do not want DI use the same OpenAPI models as HTTP
- pyiv is a hard git dependency; the HTTP/Python `run()` path hides it
