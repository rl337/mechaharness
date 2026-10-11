# Graph templates and Agentic Recipes

**Agentic Recipes** are a top-level MechaHarness concept: concrete, reusable
agent-control patterns hosts tile into larger graphs. The **substrate** is
always :class:`~mechaharness.graph_templates.base.GraphTemplate` — parameterized
subgraph factories with soft points, registry merge, and provenance stamps.
There is no second recipe executor or type system.

Clients instantiate a template/recipe, bind soft points, and may keep the
resulting concrete :class:`~mechaharness.graph.ExecutionGraph` in their own
repository. MechaHarness validates and executes those graphs without taking
ownership of client-specific realizations.

Normative requirements:
[Reusable graph recipes and typed decision plane](../requirements/recipes-and-decision-plane.md).

| Surface | Value |
|---------|-------|
| Package | `mechaharness.graph_templates` |
| Concept | Agentic Recipe (catalog id) |
| Substrate | `GraphTemplate` |
| Stability | evolving |
| Config hook | `MechaHarnessConfig.get_graph_template_registry()` |

## Catalog

First-wave candidates (existing templates; promote/document as recipes with
owning user stories):

| Catalog id | Module | Owning story | Purpose |
|------------|--------|--------------|---------|
| [fan_out_aggregate](./graph-templates/fan-out-aggregate.md) | `fan_out_aggregate` | `fangore_graph_template_soft_points` | Plan → parallel branches → reduce |
| [verify_repair](./graph-templates/verify-repair.md) | `verify_repair` | `fangore_verify_repair_recipe` | Produce → verify → bounded repair |
| [independent_review](./graph-templates/independent-review.md) | `independent_review` | `fangore_insp_independent_review` | Isolated reviewers; retain disagreement |
| [environment_repair](./graph-templates/environment-repair.md) | `environment_repair` | `fangore_environment_repair_recipe` | Diagnose → repair env → recheck |
| initialize_preflight | `initialize_preflight` | `fangore_insp_initialize_preflight` | Linkage → capability → checkpoint → ready |
| [decision_plane](./graph-templates/decision-plane.md) | `decision_plane` | `fangore_decision_plane_recipe` | Batched typed decisions + escalate |
| [bounded_retry](./graph-templates/bounded-retry.md) | `bounded_retry` | `fangore_bounded_retry_recipe` | Visible classify → permit → backoff → escalate |

Composition helpers: `GraphTemplateParams.instance_key` (namespaced ids),
`GraphTemplate.tile` (embed under a parent node). Story:
`fangore_recipe_namespace_tile`.

## Soft points

Each template declares `SoftPoint`s (tools, providers, prompts, models,
budgets, persistence, policies, runner kinds, task state). Bindings go in
`GraphTemplateParams.soft_bindings` (plus `inputs` / `branch_payloads` /
`acceptance` / `stop_contract` where applicable). Soft-point names SHOULD
describe the human decision being bound. Templates MUST NOT embed client
product policy or durable application state.

Instantiated graphs are stamped with `template_name`, `template_version`, and
`template_status` for provenance and deprecation detection. Optimize tiling
code for human readability of how recipes compose into the final graph.

## Usage sketch

```python
from mechaharness.graph_templates import (
    GraphTemplateParams,
    default_graph_templates,
)

registry = default_graph_templates()
template = registry.get("fan_out_aggregate")
assert template is not None
graph = template.instantiate(
    GraphTemplateParams(
        goal="survey sources",
        branch_payloads=[{"index": 0}, {"index": 1}],
        acceptance=["all_branches_ok"],
        soft_bindings={"fan_in_budget": 4},
    )
)
assert graph.template_name == "fan_out_aggregate"
# Bind runners for plan/branch/reduce kinds via Config, then:
# LinkageResolver → GraphExecutor.run(graph)
```

## Ownership / incubation

See [Inspiration requirements map](../inspiration/requirements-map.md) and
req 19 in [dev-blog-inspiration](../inspiration/dev-blog-inspiration.md).
Generic skeletons and Agentic Recipes live here; host-specific workflows
incubate in the client until promotion extracts a reusable recipe.
Every shipped recipe needs ≥1 owning user story that names the catalog id in
its `implementation` text.
