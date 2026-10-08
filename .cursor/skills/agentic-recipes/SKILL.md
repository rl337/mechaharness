---
name: agentic-recipes
description: >-
  Design and document MechaHarness Agentic Recipes as GraphTemplate-backed
  control patterns. Use when adding or changing graph templates, recipes,
  soft points, subgraph tiling, decision-plane or retry patterns, recipe
  catalogs, or when requirements/user stories imply a reusable agent-control
  subgraph.
---

# Agentic Recipes

**Agentic Recipe** is a top-level MechaHarness concept: a concrete, reusable
agent-control pattern. The **substrate** is always
`mechaharness.graph_templates.GraphTemplate` (params, soft points, registry,
provenance stamps). Do not invent a parallel recipe type, executor, scheduler,
persistence layer, event system, or model gateway.

Requirements:
[`docs/requirements/recipes-and-decision-plane.md`](../../../docs/requirements/recipes-and-decision-plane.md).

## When to apply

- Adding or changing anything under `src/mechaharness/graph_templates/`
- Naming, documenting, or promoting a control pattern as a recipe
- Tiling subgraphs / nesting templates into a parent `ExecutionGraph`
- Decision-plane, bounded-retry, verify-repair, fan-out, independent review,
  environment repair, initialize preflight, or similar patterns
- Auditing requirements or user stories for patterns that should become recipes
- Writing story `implementation` text that should name a recipe

## Vocabulary

| Term | Meaning |
|------|---------|
| `GraphTemplate` | Factory/API and data structure |
| Agentic Recipe | Product concept for a useful, documented, story-backed template |
| Catalog id | Stable name (`verify_repair`, `decision_plane`, …) |
| Soft point | Declared host-binding slot; name the human decision |
| Tiling | Readable composition of recipes into a parent graph |

The template-versus-recipe boundary may stay soft until a concrete case forces
it. Promote when a host would want to **read and reuse** the control story as a
named unit.

## Design rules

1. **Composition, not a second runtime.** Instantiation produces ordinary
   `ExecutionGraph` nodes/edges. Existing linkage, executor, resume, budget,
   and policy apply.
2. **Human-readable tiling.** Optimize recipe and host composition code so a
   reader can see how the final graph is built without relying only on docs.
   Prefer explicit embed/bind/wire helpers over opaque dict merges.
3. **Deterministic expand.** Same definition + version + params + parent
   binding ⇒ same graph. No model inference during construction.
4. **Namespaced identities.** Multiple instances in one parent must not collide;
   node ids should read like structure (`decision_plane/ask`).
5. **Hard structure + constrained soft points.** Callers bind declared slots;
   they must not silently mutate arbitrary internals.
6. **DI for externals.** Model runners, clocks, sleepers, effect adapters —
   inject; do not patch globals (see `di-config-ownership`).
7. **Host-extend.** Hosts add recipes by subclassing `GraphTemplate` and merging
   the registry via Config — never by forking closed enums in this repo.

## Promotion workflow

Copy and track:

```text
Recipe task:
- [ ] 1. Find the pattern in requirements and/or user stories
- [ ] 2. Decide catalog id (unambiguous leaf name)
- [ ] 3. Implement or harden as GraphTemplate (+ I/O / namespacing as needed)
- [ ] 4. Write reference docs under docs/reference/graph-templates/ (recipe label)
- [ ] 5. Ensure ≥1 owning user story; name the catalog id in implementation
- [ ] 6. Static/DI tests; data-drive matrices when coverage grows
- [ ] 7. Link story id(s) from the recipe doc; update requirements map if needed
- [ ] 8. Prefer readable tiling examples in code and docs
```

### Story obligation

Every shipped Agentic Recipe needs **at least one** user story that exercises
that recipe as the unit under test. Follow
[`user-stories`](../user-stories/SKILL.md): edit `story.json`, name the recipe
catalog id in `implementation`, regenerate the guide.

Mechanism stories (soft points / stamping / demotion) may say `GraphTemplate`.
Pattern stories **must** name the recipe catalog id.

## First-wave catalog (evaluate / promote)

| Catalog id | Module / status | Story anchors |
|------------|-----------------|---------------|
| `fan_out_aggregate` | shipped | `fangore_graph_template_soft_points`, … |
| `verify_repair` | shipped | `fangore_verify_repair_recipe` |
| `independent_review` | shipped | `fangore_insp_independent_review` |
| `environment_repair` | shipped | `fangore_environment_repair_recipe` |
| `initialize_preflight` | shipped | `fangore_insp_initialize_preflight` |
| `decision_plane` | shipped | `fangore_decision_plane_recipe` |
| `bounded_retry` | shipped | `fangore_bounded_retry_recipe` |
| *(composition)* | `instance_key` / `tile` | `fangore_recipe_namespace_tile` |

## Anti-patterns

```text
# BAD — second RecipeExecutor / recipe event bus / recipe Settings bag
# BAD — uuid node ids that make tiled graphs unreadable
# BAD — soft_bindings keys like "x" / "handler" with no human meaning
# BAD — ship a recipe with only unit tests (no owning user story)
# BAD — story implementation that describes the pattern but omits catalog id
# BAD — closed Enum of recipe names hosts must PR into

# GOOD — GraphTemplate subclass + registry merge via Config
# GOOD — readable tiling: embed(decision_plane), bind soft points, wire exits
# GOOD — implementation names verify_repair / decision_plane alongside modules
```

## Related

- [`user-stories`](../user-stories/SKILL.md) — recipe names in `implementation`
- [`project-docs`](../project-docs/SKILL.md) — recipe reference pages + TOC
- [`di-config-ownership`](../di-config-ownership/SKILL.md) — no Settings grab-bag
- [`data-driven-tests`](../data-driven-tests/SKILL.md) — recipe case matrices
- `.cursor/rules/host-extend.mdc`, `unambiguous-names.mdc`, `di-first.mdc`
- `docs/reference/graph-templates.md`
- `docs/requirements/transactional-durable-resume.md` (retry ↔ effects)
