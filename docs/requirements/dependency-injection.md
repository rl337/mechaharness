# Dependency injection requirements

## Motivation

MechaHarness is a library hosts compose through pyiv. Shared edges (HTTP,
environment, filesystem, clock, loggers, judge connection, event log) must be
**bound on Config and injected**. Lazy attribute caches on Config
(`getattr(self, "_x", None)` / construct-if-missing) and **Config `get_*`
composition** (one hook calling another to pull a collaborator) hide missing
wiring, make tests patch globals, and turn Config into a service locator.

Normative MUST/SHOULD below apply to library code under `src/mechaharness/`
and to reference tests. Host apps SHOULD follow the same pattern.

## Requirements

### DI-01: Config is the binding surface

Every shared service MechaHarness constructs for hosts MUST be registered in
`MechaHarnessConfig.configure()` (or a subclass `configure()` that calls
`super().configure()` first) via `register` / `register_instance` / map
multibind helpers.

Hosts MUST subclass Config (or use `run()` / host kit) rather than
hand-constructing harness families or stitching services outside the injector.

### DI-02: Consume by injection; fail if unbound

Dependents MUST receive shared services through constructor injection or
`injector.inject(T)`.

If a type is not bound, resolution MUST fail at inject time. Library code MUST
NOT silently construct a default instance outside `configure()` to paper over a
missing binding.

### DI-03: No getattr/hasattr service caches on Config

Config MUST NOT memoize injectables with patterns such as:

```python
existing = getattr(self, "_filesystem", None)
if existing is None:
    existing = RealFilesystem()
    self._filesystem = existing
return existing
```

pyiv singleton (or equivalent) registration is the reuse mechanism. Template
hooks (`get_inference_class()`, `get_harness_class()`, policy/registry hooks)
MAY return a **class or explicit instance for binding**; they MUST NOT stash
constructed services on `self` for later `get_*` reuse as a locator.

### DI-04: Collaborators come from the injector, not sibling `get_*`

Any hook, factory, or type that needs another injectable MUST obtain it via
constructor injection or `injector.inject(T)`.

It MUST NOT call sibling Config methods such as `self.get_event_log()`,
`self.get_environment()`, `self.get_datetime_service()`,
`self.get_logger_factory()`, `self.get_access_control()`, or similar to supply
constructor arguments.

Examples of shapes that MUST be retired (and MUST NOT be added):

| Consumer | Forbidden collaborator pull |
|----------|----------------------------|
| `get_event_log` | `self.get_logger_factory()` |
| `get_access_control` / `get_cost_accountant` | `self.get_event_log()` |
| `get_judge_connection` | `self.get_environment()` |
| `get_checkpoint_store` | `self.get_event_log()`, `self.get_datetime_service()` |
| `get_linkage_resolver` | `self.get_node_runner_registry()`, `self.get_access_control()`, … |

Rewrite as registered classes or injector factories whose constructors take
those types as parameters.

### DI-05: Settings stay slim

Lane- and provider-specific knobs belong on the owning injectable (connection
config, strategy/provider, host tool module), not as a growing bag on
`Settings`. Providers (`JudgeProvider`, `InferenceStrategy`, media providers)
MUST NEVER be Settings attributes. See `.cursor/rules/di-first.mdc` and the
`di-config-ownership` skill.

### DI-06: Stdlib and HTTP edges are first-class injectables

At minimum, Config MUST bind (defaults MAY be production implementations):

| Interface | Role |
|-----------|------|
| `Environment` | Process env for `from_env` / operator knobs |
| `DateTimeService` | UTC stamps (checkpoints, effects) |
| `Filesystem` | Decision JSONL and host paths |
| `Clock` | Monotonic time / sleep coordination |
| `LoggerFactory` | Structured logging for `LoggingEventLog` |
| `AsyncHttpClient` | Inference and judge HTTP transport |

Hosts and tests replace these by rebinding in Config (hooks that change what
`configure()` registers, `register_instance`, or `pyiv.override`), not by
monkeypatching `os.environ`, freezing wall clocks, or writing to real disk when
an injectable exists.

### DI-07: Tests prefer DI doubles over global patches

Reference and unit tests that exercise env, time, files, HTTP, loggers, model
runners, backoff/sleep, or effect adapters MUST bind doubles through Config /
override rather than patching process globals — except where no injectable seam
exists yet (then add a binding, do not grow patch surface).

### DI-08: `get_*` hooks declare bindings only

Remaining `get_*` hooks on Config MUST be limited to declaring **what**
`configure()` should register (a class, or an explicit host/test instance).
After registration, the approved read path for that service is injection.
New library code MUST NOT treat Config hooks as a service locator API.

## Testing requirements

### DI-TEST-01: Unbound inject fails

A test MUST show that requesting an unbound injectable raises rather than
constructing a hidden default.

### DI-TEST-02: Overlay / hook doubles

A test MUST show Memory/Mock (or equivalent) doubles for at least one stdlib
edge and HTTP client via Config overlay or hook, without `monkeypatch` of
`os.environ` / filesystem / time for that path.

### DI-TEST-03: Composed services inject collaborators

A test MUST prove that at least one composed default (e.g. checkpoint store or
access control) receives a rebound collaborator (`EventLog`,
`DateTimeService`, or `Environment`) through the injector when the collaborator
binding is overridden — without the composed hook calling `self.get_*` for that
collaborator once the DI-04 rewrite lands.

## Related

- Guide: [Dependency injection](../guides/dependency-injection.md)
- Architecture: [Dependency injection](../architecture.md#dependency-injection)
- Skill: `.cursor/skills/di-config-ownership/SKILL.md`
- Rule: `.cursor/rules/di-first.mdc`
- Recipe tests: [TEST-02](./recipes-and-decision-plane.md#test-02-dependency-injection)
