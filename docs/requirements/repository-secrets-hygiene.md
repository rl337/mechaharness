# Repository secrets and local-config hygiene

## Motivation

MechaHarness is a **public** library. Git history is durable and often mirrored.
Personal machine layout, private LAN topology, and any authentication material
must never enter the tracked tree — tip **or** history.

This page is normative for maintainers and coding agents working in this
repository. It complements host-side rules in
[Host integration](./host-integration.md) (payloads MUST NOT carry secrets) and
the project-docs quality bar (no secrets in examples).

## Requirements

### SEC-01: No authentication material in git

Commits MUST NOT introduce:

- API keys, PATs, OAuth/refresh tokens, session cookies, or private keys
- `.env` / `.env/` contents, `credentials*`, `.pypirc`, or similar secret stores
- Literal bearer strings in docs, tests, fixtures, CI logs committed as artifacts,
  or example blocks

Placeholders (`local`, `lm-studio`, `<served-model-id>`, empty env defaults) are
allowed. Operators MUST supply real credentials via the environment, a secret
store, or gitignored local files (see SEC-03).

If a secret is ever committed, maintainers MUST rotate it and treat tip-only
deletion as insufficient — rewrite or otherwise purge history, and assume public
exposure until rotation completes.

### SEC-02: No personal or lab-private endpoints in tracked content

Tracked sources, docs, fixtures, and CI config MUST NOT embed:

- Private/RFC1918 lab IPs or hostnames used only on a maintainer network
- Absolute home-directory paths (`/Users/…`, `/home/…`) as the documented
  contract for clones
- Maintainer-only MCP/agent wiring that only works on one machine

Public loopback examples (`http://127.0.0.1:…`, `http://localhost:…`) and
placeholder tokens such as `/ABS/PATH/to/project` or
`<openai-compat-base-url>` MUST be used instead. Library defaults MUST NOT
point at a private LAN host (hosts set `MECHA_BASE_URL` / Settings).

### SEC-03: Machine-local operator files stay gitignored

The following (and equivalents) MUST remain untracked and listed in
`.gitignore`:

| Path | Role |
|------|------|
| `.env/` | Operator `env.sh`, MCP launcher secrets |
| `.cursor/mcp.json` | Cursor MCP absolute paths |
| `.codex/` | Codex MCP absolute paths / local model ids |
| `.mechaharness/` | Local generator run state |

Tracked **examples** (``.env.example``,
`docs/guides/codex-mcp.config.toml.example`, docs snippets) MUST use
placeholders only. Copying an example into a gitignored path is the supported
operator workflow.

### SEC-04: Docs and inspiration name roles, not private hosts

Inspiration notes, guides, and requirements MUST NOT name private host repos or
link into them. Describe hosts by role (for example “video production project”).
Personal lab model inventory tables that only a maintainer can reach MUST NOT
ship as the canonical how-to; prefer generic OpenAI-compat loopback examples.

### SEC-05: Pre-commit / review gate

Before merge, authors and reviewers MUST confirm the diff introduces no SEC-01
or SEC-02 material. Agents following project-docs MUST treat secrets-in-examples
as a docs defect. CI MAY add scanners later; absence of a scanner does not
weaken SEC-01..04.

## Related

- [Local OpenAI-compat](../guides/openai-local.md) — loopback examples + local MCP
- [Durable graph generators](../reference/durable-graph-generators.md) — gitignored MCP wiring
- [Host integration HOST-05](./host-integration.md) — EventLog payloads MUST NOT carry secrets
- [`.env.example`](../../.env.example) — tracked operator template
