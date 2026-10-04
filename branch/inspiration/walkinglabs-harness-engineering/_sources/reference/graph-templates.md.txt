# Graph templates

Reusable parameterized **subgraph skeletons** owned by MechaHarness. Clients
instantiate a template, bind soft points, and may keep the resulting concrete
:class:`~mechaharness.graph.ExecutionGraph` in their own repository.
MechaHarness validates and executes those graphs without taking ownership of
client-specific realizations.

| Surface | Value |
|---------|-------|
| Package | `mechaharness.graph_templates` |
| Stability | evolving |
| Config hook | `MechaHarnessConfig.get_graph_template_registry()` |

## Catalog

| Template | Module | Purpose |
|----------|--------|---------|
| [fan_out_aggregate](./graph-templates/fan-out-aggregate.md) | `fan_out_aggregate` | Plan → parallel branches → reduce |
| [verify_repair](./graph-templates/verify-repair.md) | `verify_repair` | Produce → verify → bounded repair |
| [independent_review](./graph-templates/independent-review.md) | `independent_review` | Isolated reviewers; retain disagreement |
| [environment_repair](./graph-templates/environment-repair.md) | `environment_repair` | Diagnose → repair env → recheck |

## Soft points

Each template declares `SoftPoint`s (tools, providers, prompts, models,
budgets, persistence, policies, runner kinds, task state). Bindings go in
`GraphTemplateParams.soft_bindings` (plus `inputs` / `branch_payloads` /
`acceptance` / `stop_contract` where applicable). Templates MUST NOT embed
client product policy or durable application state.

Instantiated graphs are stamped with `template_name`, `template_version`, and
`template_status` for provenance and deprecation detection.

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
Generic skeletons live here; host-specific workflows incubate in the client
until promotion extracts a reusable template.
