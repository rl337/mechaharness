# Guided coding (`guided_coding`)

**Agentic Recipe.** Frontier driver (Cursor MCP) answers short engineering
guidance; local `openai_local` inference classifies **oneshot vs todo list**,
implements under workspace tools with pre/item/post acceptance, then an
**audited infer-accept** tile gates quality (RDG-aligned). Token-heavy coding
stays off the Cursor account.

| Surface | Value |
|---------|-------|
| Catalog id | `guided_coding` |
| Module | `mechaharness.graph_templates.guided_coding` |
| Host Config | `mechaharness.project_coding.ProjectCodingConfig` |
| Substrate | `GraphTemplate` (tiles `instruction_todo_plan` + `audited_infer_accept`) |
| Owning stories | `fangore_guided_coding_recipe` |

## When to use

- Cursor (or another MCP client) should guide approach/constraints only
- Local OpenAI-compat models should edit files and run tests in the project tree
- Instructions may be a oneshot or an ordered list (with conflict refine + post-list AC)
- Quality gate needs distinct decide/QA principals + frozen criteria (not only `verify_repair`)

## Soft points

| Name | Kind | Role |
|------|------|------|
| `external_guidance` | guidance (required) | Frontier engineering direction (`advice_requested`) |
| `max_iterations` / `max_items` / `stop_contract` | budget | Bound per-item tool loops and todo count |
| `acceptance` | policy | Criteria forwarded to plan + `audited_infer_accept` |
| `decide_principal` / `qa_principal` | policy | Audit tile principals (must differ) |

Optional plan refinement (`scope_refinement` / `list_refinement`) lives on the
tiled `instruction_todo_plan` and is requested dynamically when needed.

Before the Completer runs, local work **preflights** `verify_runs`. If they
already pass, it reports `already_satisfied` / `changes_expected=false` and
skips implementation (Python validate is the proof). Stories that assert
`written_files` should use `includes_if` gated on `changes_expected`.

After coding `verify_runs` / work-item failure, local work may **restore the
pre-burst workspace**, retry once with a consolidated restore-and-finish brief,
and if that still fails yield `decompose` guidance so the frontier driver can
clarify (see
[Instruction todo plan](./instruction-todo-plan.md#failure-escalate-restore--consolidated-retry--guidance)).

## Node components

| Parent graph node | Components |
|-------------------|------------|
| `brief` | `soft_point` (`external_guidance` / `guidance_request`) |
| `plan_tile` | `child_graph` (tiled `instruction_todo_plan`) |
| `audit_tile` | `child_graph` (tiled `audited_infer_accept`) |

See [Node components](../node-components.md),
[Instruction todo plan](./instruction-todo-plan.md), and
[Audited infer-accept](./audited-infer-accept.md).

## MCP wiring

Inference endpoints belong on the Cursor MCP server `env` block (not a required
project `.env`). Set `MECHA_MCP_HOST=project_coding` so the stdio adapter builds
`ProjectCodingConfig`. See [Durable graph generators](../durable-graph-generators.md).

## Related

- [Instruction todo plan](./instruction-todo-plan.md)
- [Audited infer-accept](./audited-infer-accept.md)
- [Local OpenAI-compat](../../guides/openai-local.md)
