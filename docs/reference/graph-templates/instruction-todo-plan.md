# Instruction todo plan (`instruction_todo_plan`)

**Agentic Recipe.** Classify the current instruction as a **oneshot** or an
ordered **todo list**, refine the list for conflicts, freeze pre-list
acceptance, execute each item with per-item verify, then check **post-list**
acceptance so later steps have not undone earlier ones. Human calling
refinement returns as generator `advice_requested`; answering restarts the
plan with `guidance_history`.

| Surface | Value |
|---------|-------|
| Catalog id | `instruction_todo_plan` |
| Module | `mechaharness.graph_templates.instruction_todo_plan` |
| Domain | `mechaharness.instruction_plan` |
| Substrate | `GraphTemplate` |
| Owning stories | `fangore_instruction_todo_plan` |

## Stages

```text
classify → refine_plan → pre_accept → work_item* → item_accept → post_accept → complete
```

| Stage | Role |
|-------|------|
| `classify` | oneshot vs list (inputs or soft evidence) |
| `refine_plan` | conflict check vs post-list acceptance |
| `pre_accept` | freeze / verify criteria before work |
| `work_item` | repeating execute (oneshot = one iteration) |
| `item_accept` | per-todo acceptance |
| `post_accept` | holistic check after the full list |
| `complete` | terminal |

## Soft points

| Name | Kind | Role |
|------|------|------|
| `scope_refinement` | guidance (optional) | Asked only when local work cannot classify |
| `list_refinement` | guidance (optional) | Asked when conflicts would fail post-accept |
| `max_items` / `stop_contract` | budget | Bound the `work_item` loop |
| `pre_acceptance` / `item_acceptance` / `post_acceptance` | policy | Three acceptance layers |
| `*_kind` | runner_kind | Override `instruction.*` node kinds |

Required guidance soft points are auto-queued at generator start. Optional
guidance soft points are **not** auto-queued — local work returns
`request_guidance` and `DurableGraphGenerator._advance` yields, then restarts
after resume.

## Node components

| Parent graph node | Components |
|-------------------|------------|
| `classify` | `soft_point` (`scope_refinement` / `guidance_request` when yielded) |
| `refine_plan` | `soft_point` (`list_refinement`) |
| `pre_accept` / `item_accept` / `post_accept` | `soft_point` (acceptance policies) |
| `work_item` | `stop_contract`, `soft_point` (`max_items`) |

See [Node components](../node-components.md).

## Related

- [Guided coding](./guided-coding.md) — tiles this recipe as `plan_tile`
- [Durable graph generators](../durable-graph-generators.md) — `request_guidance` restart
