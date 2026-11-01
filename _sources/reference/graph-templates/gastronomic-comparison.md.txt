# Template: gastronomic_comparison

Assemble and validate a comparable A/B/C/D trial record for
`guided_coding` vs `gastronomic_guided_development`. Summaries never declare a
single-run winner.

| Item | Value |
|------|-------|
| Name | `gastronomic_comparison` |
| Module | `mechaharness.graph_templates.gastronomic_comparison` |
| Class | `GastronomicComparisonTemplate` |
| Version | `1` |

## When to use

- After a gastronomic (or baseline) run finishes and host metrics are known
- When logging fair comparison trials for the calculator suite benchmark

## Topology

```text
seed → assemble (comparison_assemble) → validate (comparison_validate)
```

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `compare_payload` | task_state | `trial_id` / `arm` / `recipe_id` / `suite_id` |

## Node components

| Graph node | Components |
|------------|------------|
| `assemble` | `soft_point` (`compare_payload`) |

## Stories

Suite `fangore_gastronomic_comparison` (`005` trial, `010` summary, `015` shape).

## Guide

[Gastronomic comparison protocol](../../guides/gastronomic-comparison.md).
