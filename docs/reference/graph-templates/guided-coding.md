# Guided coding (`guided_coding`)

**Agentic Recipe.** Frontier driver (Cursor MCP) answers short engineering
guidance; local `openai_local` inference and workspace tools implement; an
**audited infer-accept** tile gates quality (RDG-aligned). Token-heavy coding
stays off the Cursor account.

| Surface | Value |
|---------|-------|
| Catalog id | `guided_coding` |
| Module | `mechaharness.graph_templates.guided_coding` |
| Host Config | `mechaharness.project_coding.ProjectCodingConfig` |
| Substrate | `GraphTemplate` (tiles `conversational_tool_loop` + `audited_infer_accept`) |
| Owning stories | `fangore_guided_coding_recipe` |

## When to use

- Cursor (or another MCP client) should guide approach/constraints only
- Local OpenAI-compat models should edit files and run tests in the project tree
- Quality gate needs distinct decide/QA principals + frozen criteria (not only `verify_repair`)

## Soft points

| Name | Kind | Role |
|------|------|------|
| `external_guidance` | guidance | Frontier engineering direction (`advice_requested`) |
| `max_iterations` / `stop_contract` | budget | Bound the code tool loop |
| `acceptance` | policy | Criteria forwarded to `audited_infer_accept` |
| `decide_principal` / `qa_principal` | policy | Audit tile principals (must differ) |

## Node components

| Parent graph node | Components |
|-------------------|------------|
| `brief` | `soft_point` (`external_guidance` / `guidance_request`) |
| `code_loop` | `child_graph` (tiled `conversational_tool_loop`), `soft_point` |
| `audit_tile` | `child_graph` (tiled `audited_infer_accept`) |

See [Node components](../node-components.md) and
[Audited infer-accept](./audited-infer-accept.md).

## MCP wiring

Inference endpoints belong on the Cursor MCP server `env` block (not a required
project `.env`). Set `MECHA_MCP_HOST=project_coding` so the stdio adapter builds
`ProjectCodingConfig`. See [Durable graph generators](../durable-graph-generators.md).

## Related

- [Conversational tool loop](./conversational-tool-loop.md)
- [Audited infer-accept](./audited-infer-accept.md)
- [Local OpenAI-compat](../../guides/openai-local.md)
