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
| Config hook | `MechaHarnessConfig.graph_template_classes()` → pyiv `contribute_map` / `catalog_keys(GraphTemplate)`; inject `GraphTemplateRegistry` |

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
| [produce_critique_refine](./graph-templates/produce-critique-refine.md) | `produce_critique_refine` | `fangore_insp_produce_critique_refine` | Produce → isolated critique → bounded refine |
| [safety_eval](./graph-templates/safety-eval.md) | `safety_eval` | `taloneth_insp_safety_eval_recipes` | Scenario → isolated review → deterministic safety score |
| [conversational_tool_loop](./graph-templates/conversational-tool-loop.md) | `conversational_tool_loop` | `fangore_conversational_tool_loop` | Expandable tools → inference / tool_call rounds |
| [guided_coding](./graph-templates/guided-coding.md) | `guided_coding` | `fangore_guided_coding_recipe` | Frontier guidance → instruction plan → audited gate |
| [instruction_todo_plan](./graph-templates/instruction-todo-plan.md) | `instruction_todo_plan` | `fangore_instruction_todo_plan` | Oneshot vs list; refine; pre/item/post acceptance |
| [audited_infer_accept](./graph-templates/audited-infer-accept.md) | `audited_infer_accept` | `fangore_audited_infer_accept` | Collect → freeze → decide → QA → deterministic → gate |
| [workspace_discovery](./graph-templates/workspace-discovery.md) | `workspace_discovery` | `fangore_workspace_discovery_found` | Read-only evidence inventory (`found`/`not_found`/…) |
| [contract_extraction](./graph-templates/contract-extraction.md) | `contract_extraction` | `fangore_contract_extraction_found` | Freeze inventory into typed `ChangeContract` |
| [change_decomposition](./graph-templates/change-decomposition.md) | `change_decomposition` | `fangore_change_decomposition_ordered` | Ordered ChangePlan slices from a contract |
| [change_execution](./graph-templates/change-execution.md) | `change_execution` | `fangore_change_execution_apply` | Scoped slice apply with diff + hashes |
| [change_verification](./graph-templates/change-verification.md) | `change_verification` | `fangore_change_verification_host` | Host-observed VerificationReport |
| [gastronomic_guided_development](./graph-templates/gastronomic-guided-development.md) | `gastronomic_guided_development` | `fangore_gastronomic_guided_development_shape` | Product tile: discovery → … → verify |

Composition helpers: `GraphTemplateParams.instance_key` (namespaced ids),
`GraphTemplate.tile` (embed under a parent node). Story:
`fangore_recipe_namespace_tile`.

Node components (sub-node elements inside a graph node):
[Node components](./node-components.md).

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

## Versions, promotion, and evolution allowlist

`GraphTemplateRegistry` stores every registered version of a catalog id.
`register` activates a template (legacy replace-by-name); `add_version` stores
an immutable candidate that stays inactive until `promote(name, version)`
moves the active pointer. `rollback(name)` restores the previous target, and
`get(name, version=...)` reads any stored version. Hosts own eval results and
promotion policy; the registry owns only the reversible pointer.

`SoftPoint.evolvable` (default `False`) is the declared evolution allowlist:
an optimizer may rewrite only evolvable soft points, enforced by
`GraphTemplate.assert_evolution_allowed`. Graph topology, grants, and stop
contracts are hard structure.

### Promotion surfaces (host orientation)

| Intent | API |
|--------|-----|
| Catalog pointer + held-out gate + host opinion | `promote_recipe(registry, policy, request, hooks)` in `recipe_lifecycle.recipe_promotion_policy` (re-exported by `host_apis`) |
| Catalog pointer + held-out gate only | `registry.promote_with_final_test(name, version, final_test=...)` |
| Ungated pointer move (advanced / migration) | `registry.promote(name, version)` |
| Offline research candidate | `ResearchLab.promote` |
| Soft instruction → hard rule | `rule_promotion.promote_soft_to_hard` |

Prefer `promote_recipe` for product hosts: it applies
`MechaHarnessConfig.get_recipe_promotion_policy()` then the held-out gate.
`promote` remains an ungated pointer move for hosts that run their own gate.
Campaigns use `get_evolution_campaign_hooks()` (no-op defaults); pass them as `hooks` and `promote_recipe` calls `on_promotion` after a successful move. Typed-port search is `registry.search_compatible(...)`. The same
held-out gate guards `ResearchLab.promote`.

## Recipe comparison (do not merge)

| Catalog id | Control story |
|------------|---------------|
| `produce_critique_refine` | Produce → critique → refine loop with evolvable soft points |
| `independent_review` | Isolated multi-reviewer context (adversarial optional) |
| `verify_repair` | Oracle / verify then repair until stop |
| `safety_eval` | Produce → isolated review → deterministic score (measure-only) |
| `decision_plane` | Bounded decision surfaces with policy / shadow / telemetry |
| `workspace_discovery` | Read-only workspace evidence → typed inventory |
| `contract_extraction` | Freeze priors → typed ChangeContract |
| `change_decomposition` | Contract → ordered ChangePlan slices |
| `change_execution` | Approved slice → scoped writes → ChangeExecution |
| `change_verification` | ChangeExecution + contract → host VerificationReport |
| `gastronomic_guided_development` | Product composition (discovery → … → verify; diagnose deferred) |

These are distinct Agentic Recipes on the same `GraphTemplate` substrate.

## Typed ports and candidate search

A template may declare `io_contract` (a `TemplateIOContract` of typed input and
output ports). `search_compatible_recipes(registry, required_inputs,
required_outputs)` returns the catalog ids whose ports fit; it never builds a
graph, and recipes without an `io_contract` are not candidates. Hosts
can bound optimizer candidates with `recipe_evolution.propose_candidates`, which
emits soft-binding dicts only and validates them against the registry and the
evolvable allowlist.

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
