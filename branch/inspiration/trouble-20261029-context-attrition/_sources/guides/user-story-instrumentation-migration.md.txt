# Probe-case → instrumented user-story migration

| Surface | Value |
|---------|-------|
| Status | Wave 3 landed for P2–P4 case-bag removal; P3 demotions **retracted** |
| Gold pattern | soft-bind / corpus inputs → product CLI verb → cassette/live |
| Next | [Recipe expansion waves](./user-story-recipe-expansion.md) (G0+) |

## Litmus

A user story is valid only if a persona can walk it through the **product CLI
verb surface**: real inputs in, real lane or recipe execution, hard observables
out. Case-bag verbs (`decision_case`, `lifecycle_case`) failed this litmus and
have been **removed**.

**Clarification (post Wave 3):** If the claim is a valid product story and the
graph path is missing, **add the recipe/runners** — do not demote the story to
unit-only. Unit tests still cover helpers; stories own the walk.

## Landed product surfaces

| Verb / recipe | Role |
|---------------|------|
| `judge` | Judge-lane one-shot (infer twin) |
| `judge_route` | Judge + JudgementPolicy |
| `context_pack` (`run_recipe`) | `RagRetriever` → `assemble_context_within_budget` |
| `assemble_context` | Thin pack leaf for already-scored candidates |
| `tool_lifecycle` | Config-bound lifecycle extensions (tool or graph) |
| `instantiate_recipe` | Soft-bind / shape (interim until execute runners exist) |

## G0 restored (decision-plane execute)

Restored under `run_recipe` + `DecisionPlaneRecipeAdapter` /
`decision_plane_runner` (fixture answers on bind `inputs`):

- `fangore_decision_plane_projection`
- `fangore_decision_plane_policy`
- `fangore_decision_plane_shadow`
- `fangore_decision_plane_telemetry`

Also promoted `fangore_decision_plane_recipe` /
`fangore_decision_plane_model_policy` from instantiate-only to execute.
Helpers remain unit-covered in
[`tests/test_decision_plane_runtime.py`](../../tests/test_decision_plane_runtime.py).

## Related

- [User-story recipe expansion](./user-story-recipe-expansion.md)
- [User-story migration batches](./user-story-migration-batches.md)
- [Jev typed-judgment inspiration](../inspiration/jev-typed-judgment-inspiration.md)
- Gold judge stories: `fangore_refund_verdict`, citation `fangore_jev_citation_*`
