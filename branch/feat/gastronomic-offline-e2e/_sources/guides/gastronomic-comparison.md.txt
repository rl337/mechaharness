# Gastronomic comparison protocol

After M6, `gastronomic_guided_development` publishes a host-gated
`DevelopmentOutcome`. This guide records how to compare it fairly against the
unchanged `guided_coding` baseline.

Do **not** claim reliability improvement from one stochastic run or an unfair
inference budget.

## Arms

| Arm | Recipe | Typical model |
|-----|--------|---------------|
| A | `guided_coding` | local Qwen (baseline) |
| B | `gastronomic_guided_development` | same local Qwen |
| C | `guided_coding` | stronger model (capability control) |
| D | `gastronomic_guided_development` | stronger model (optional) |

Use the sequential `calc_cli` suite (or an equivalently staged calculator
workspace) with the same acceptance checks, tools, and budgets for A vs B.

## What to record

Use `mechaharness.gastronomic_comparison.assemble_gastronomic_trial`:

- `trial_id`, `arm`, `recipe_id`, `suite_id`
- `development_outcome` when the gastronomic product finishes
- metrics: stages passed/total, prior regressions, first failure class,
  model calls, prompt/completion tokens, tool calls, wall time, repair loops,
  guidance yields, repeat-failure loops, verified edits
- model id/settings and budget limits

Aggregate with `summarize_gastronomic_comparison`. The summary never sets a
`winner`; hosts interpret under matched budgets.

## Offline vs live

- Offline Fangore stories prove trial-record shape and arm/recipe pairing.
- Suite `fangore_gastronomic_offline_e2e` walks verify → diagnose → revise →
  accept → comparison on a calculator fixture and records completed/failed
  trials without a live model.
- Live A/B runs are opt-in when the host has the configured endpoint. Mark
  **not run** rather than fabricating results.

## Related

- Recipe: [`gastronomic_guided_development`](../reference/graph-templates/gastronomic-guided-development.md)
- Baseline: [`guided_coding`](../reference/graph-templates/guided-coding.md)
- Plan: [`gastronomic-guided-development-execution-plan.md`](../inspiration/gastronomic-guided-development-execution-plan.md)
- Suite map: [`coding-delegate-suites.md`](./coding-delegate-suites.md)
