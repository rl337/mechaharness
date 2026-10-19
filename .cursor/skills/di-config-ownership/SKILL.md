---
name: di-config-ownership
description: >-
  Keep Settings slim and bind shared services via MechaHarnessConfig + pyiv
  injection (no getattr/hasattr lazy caches; no get_* composition). Use when
  adding Settings fields, backends, lanes, judge/media/reason connections,
  APIConnectionConfig, JudgeProvider wiring, stdlib edges (Environment,
  Filesystem, Clock, DateTimeService, LoggerFactory), AsyncHttpClient,
  EventLog / AccessControl / CheckpointStore / LinkageResolver wiring,
  Agentic Recipe / graph-template configuration, or when tempted to memoize
  services on Config or call sibling get_* from another hook/factory.
---

# DI config ownership

MechaHarness is pyiv DI-first. **Settings is not a provider bag.** Shared
services are **Config bindings**, not lazy attributes on `self`. Callers that
need those services **inject them** — they do not call Config `get_*` hooks.

## When to apply

- Adding or changing `Settings` fields
- Adding a lane (reason / judge / media) or HTTP connection
- Wiring `JudgeProvider`, `InferenceStrategy`, or future media providers
- Wiring Agentic Recipes / `GraphTemplateRegistry` (never put recipe catalogs
  or model picks on Settings)
- Binding pyiv stdlib edges (`Environment`, `Filesystem`, `Clock`,
  `DateTimeService`, `LoggerFactory`) or `AsyncHttpClient`
- Wiring composed services (`EventLog`, `AccessControl`, `CheckpointStore`,
  `LinkageResolver`, cost accountant, judge connection)
- Tempted to put `*_base_url`, OAuth, or provider instances on `Settings`
- Tempted to write `getattr(self, "_x", None)` / `hasattr` caches for services
- Tempted to call `self.get_event_log()` / `self.get_environment()` / etc. from
  another hook, factory, or domain type

## Checklist

1. **Name the owner injectable** — connection config, strategy/provider, stdlib
   interface, or host tool module — not Settings.
2. **Put knobs on that type** — constructor args and/or `from_env()` (e.g.
   `SimpleHttpConnectionConfig.from_env` for `MECHA_JUDGE_*`).
3. **Bind in `configure()`** — `self.register(...)` / `self.register_instance(...)`
   (or class-bind). Prefer returning a **class** from hooks so pyiv constructs
   and injects deps; use instances only for host/test doubles.
4. **Consume via injection** — constructor args or `injector.inject(T)`. Any
   type that needs `EventLog`, `Environment`, `DateTimeService`, etc. takes
   them as constructor parameters (or a factory uses `inject()`).
5. **Fail if unbound** — missing bindings raise at inject time. Do not silently
   construct a default outside `configure()`.
6. **Scrutinize `get_*` callers** — if a hook/factory/domain object calls
   another `get_*` to obtain a collaborator, rewrite it to inject that
   collaborator instead.
7. **Env for operators** — document env on the owning type’s docs; do not mirror
   every env into Settings.
8. **Do not add to Settings** unless the knob is truly cross-cutting run surface
   (and prefer shrinking Settings over time).
9. **Never** store `JudgeProvider` / `InferenceStrategy` / media providers as
   Settings attributes.
10. **Never** use `getattr(self, "_service", None)` / `hasattr` lazy caches as a
    substitute for pyiv singletons.

## Bind, don't memoize; inject, don't `get_*`

```python
# BAD — Config as service locator / lazy cache
def get_filesystem(self) -> Filesystem:
    existing = getattr(self, "_filesystem", None)
    if existing is None:
        existing = RealFilesystem()
        self._filesystem = existing
    return existing

# BAD — composed service pulls collaborators via getters
def get_checkpoint_store(self) -> CheckpointStore:
    return EventLogCheckpointStore(
        GraphStore(self.get_event_log(), agent_id="graph"),
        event_log=self.get_event_log(),
        datetime_service=self.get_datetime_service(),
    )

def get_access_control(self) -> AccessControl:
    return InMemoryAccessControl(
        event_log=self.get_event_log(),
        policy=self.get_access_policy(),
    )

def get_judge_connection(self) -> APIConnectionConfig:
    return SimpleHttpConnectionConfig.for_judge(env=self.get_environment())

# GOOD — bind interfaces in configure(); composed types take ctor deps
def configure(self) -> None:
    super().configure()
    self.register(Filesystem, RealFilesystem, singleton=True)
    self.register(LoggerFactory, StdlibLoggerFactory, singleton=True)
    self.register(DateTimeService, PythonDateTimeService, singleton=True)
    self.register(Environment, OsEnvironment, singleton=True)
    self.register(EventLog, FanoutEventLog, singleton=True)  # ctor injects LoggerFactory
    self.register(AccessControl, InMemoryAccessControl, singleton=True)
    self.register(CheckpointStore, EventLogCheckpointStore, singleton=True)
    self.register(APIConnectionConfig, make_judge_connection, singleton=True)

def make_judge_connection(injector: Injector) -> APIConnectionConfig:
    return SimpleHttpConnectionConfig.for_judge(
        env=injector.inject(Environment),
    )
```

### What `get_*` hooks are for

Template hooks (`get_inference_class()`, `get_harness_class()`,
`get_access_policy()`, map hooks like `inference_classes()`) **declare what to
bind**. They return a type or an explicit override instance.

They are **not** a runtime service locator. Do not call them from other hooks,
factories, or library types to fetch already-bound collaborators. Once
`configure()` has registered `T`, the only approved read path is
`inject(T)` / constructor injection.

Hosts override hooks so `configure()` registers a different class or instance.
Tests use `register_instance`, hook overrides, or
`pyiv.override(base).with_(overlay)` — not monkeypatching `os.environ`,
freezing time, or writing to real disk when an injectable exists.

### Debt to retire (scrutinize these)

Call sites that still compose via `get_*` (e.g. `get_event_log` →
`get_logger_factory`, `get_checkpoint_store` → `get_event_log` /
`get_datetime_service`, `get_linkage_resolver` → `get_access_control` / …,
`get_cost_accountant` → `get_event_log`, `get_judge_connection` →
`get_environment`) MUST be rewritten to register classes/factories that
**inject** those deps. Do not add new call sites of this shape.

## Lane map (outcomes ≠ Settings)

| Lane | Outcome | Provider (DI) | Connection |
|------|---------|---------------|------------|
| reason | `Completion` | `InferenceStrategy` | later connection; today transitional Settings `base_url` |
| judge | `Judgement` | `JudgeProvider` | `APIConnectionConfig` |
| media | `Generation` | host / later provider | host — never new Settings fields |

## Anti-patterns

```python
# BAD
Settings.judge_base_url = ...
Settings.media_url = ...
Settings.judge_provider = SystemOneJudgeProvider(...)
getattr(self, "_environment", None)  # lazy service cache
self.get_event_log()  # from another hook/factory as a collaborator

# GOOD
SimpleHttpConnectionConfig.from_env()  # or explicit ctor
MechaHarnessConfig.configure() binds Environment / APIConnectionConfig
injector.inject(APIConnectionConfig)  # fails if unbound
class MyService:
    def __init__(self, event_log: EventLog, env: Environment) -> None: ...
```

Recipe soft points bind host-owned tools/prompts/models via Config and
injectables. Model size/provider for a decision recipe is routing policy
(Completer / JudgeProvider flavors), not Settings fields and not hard-coded
into the recipe architecture. See
[`agentic-recipes`](../agentic-recipes/SKILL.md).

See `.cursor/rules/di-first.mdc`, `docs/requirements/dependency-injection.md`,
and `docs/architecture.md` (Dependency injection).
