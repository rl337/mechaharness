---
name: di-config-ownership
description: >-
  Keep Settings slim: lane/provider knobs belong on owning injectables and
  MechaHarnessConfig hooks. Use when adding Settings fields, backends, lanes,
  judge/media/reason connections, APIConnectionConfig, or JudgeProvider wiring.
---

# DI config ownership

MechaHarness is pyiv DI-first. **Settings is not a provider bag.**

## When to apply

- Adding or changing `Settings` fields
- Adding a lane (reason / judge / media) or HTTP connection
- Wiring `JudgeProvider`, `InferenceStrategy`, or future media providers
- Tempted to put `*_base_url`, OAuth, or provider instances on `Settings`

## Checklist

1. **Name the owner injectable** — connection config, strategy/provider, or host tool module — not Settings.
2. **Put knobs on that type** — constructor args and/or `from_env()` (e.g. `SimpleHttpConnectionConfig.from_env` for `MECHA_JUDGE_*`).
3. **Expose via Config hook** — `get_judge_connection()`, `get_judge_provider()`, `get_inference_class()`, etc. Register in `configure()`.
4. **Env for operators** — document env on the owning type’s docs; do not mirror every env into Settings.
5. **Do not add to Settings** unless the knob is truly cross-cutting run surface (and prefer shrinking Settings over time).
6. **Never** store `JudgeProvider` / `InferenceStrategy` / media providers as Settings attributes.

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

# GOOD
SimpleHttpConnectionConfig.from_env()  # or explicit ctor
MechaHarnessConfig.get_judge_connection() / get_judge_provider()
```

See `.cursor/rules/di-first.mdc` and `docs/architecture.md` (Dependency injection).
