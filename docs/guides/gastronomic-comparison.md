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
- Arm A (baseline): run sequential `calc_cli` under
  `MECHA_STORY_BACKEND=live` + `MECHA_BASE_URL` + `MECHA_MODEL`, then record a
  trial from the suite run directory:

```bash
MECHA_STORY_BACKEND=live MECHA_BASE_URL=<openai-compat-base-url> \
  MECHA_MODEL=<served-model-id> MECHA_MAX_TOKENS=8192 \
  pytest -s -q tests/stories/test_user_story_suites.py -k calc_cli

python scripts/record_gastronomic_comparison_trial.py \
  --suite-run .mechaharness/suite_runs/$(cat .mechaharness/suite_runs/calc_cli.latest) \
  --trial-id calc-a-1 --arm A --recipe guided_coding \
  --model-id "$MECHA_MODEL"
```

- Arm B stays **`not_run`** until `gastronomic_guided_development` can drive
  Completer coding comparable to `guided_coding` + `project_coding` (today
  execute applies host `file_revisions` only). Use
  `live_comparison_status` / `comparison_live_status` so status JSON never
  invents a B trial.

## Related

- Recipe: [`gastronomic_guided_development`](../reference/graph-templates/gastronomic-guided-development.md)
- Baseline: [`guided_coding`](../reference/graph-templates/guided-coding.md)
- Plan: [`gastronomic-guided-development-execution-plan.md`](../inspiration/gastronomic-guided-development-execution-plan.md)
- Suite map: [`coding-delegate-suites.md`](./coding-delegate-suites.md)
