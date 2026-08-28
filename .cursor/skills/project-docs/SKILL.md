---
name: project-docs
description: >-
  Create and maintain MechaHarness project documentation under docs/.
  Use when writing, updating, restructuring, or reviewing docs; when the user
  mentions documentation, docs/, README sync, architecture notes, guides, or
  API/CLI reference pages for this project.
---

# MechaHarness project docs

Maintain documentation in `docs/` so it stays accurate with the codebase and
usable as the source of truth for humans and agents.

## When to apply

- Creating or editing anything under `docs/`
- Syncing `README.md` with deeper docs
- Documenting architecture, inference backends, harness families, CLI, or API
- User asks to "update the docs", "add a guide", or "document X"

## Layout

```text
docs/
  logo.png              # Project logo (canonical asset)
  index.md              # Docs home / table of contents
  architecture.md       # Design: Strategy + harness hierarchy
  guides/               # How-to guides (install, local models, extend)
  reference/            # Stable contracts (types, CLI, HTTP API)
  adr/                  # Architecture Decision Records (optional)
```

Keep `README.md` short: logo, one-line pitch, install/quick start, and links
into `docs/`. Do not duplicate long reference material in the README.

## Workflow

Copy and track:

```text
Docs task:
- [ ] 1. Identify audience and doc type (guide / reference / architecture / ADR)
- [ ] 2. Read current code + existing docs for the topic
- [ ] 3. Create or update the target page under docs/
- [ ] 4. Update docs/index.md TOC if a page was added/renamed/removed
- [ ] 5. Update README.md links only if the entry surface changed
- [ ] 6. Verify commands, module paths, and env var names against the repo
```

### Create a new page

1. Choose the correct folder (`guides/`, `reference/`, `adr/`, or top-level).
2. Use kebab-case filenames (`local-inference.md`, not `Local Inference.md`).
3. Start from the templates in [templates.md](templates.md).
4. Link the page from `docs/index.md`.
5. Prefer relative links (`./architecture.md`, `../guides/install.md`).

### Update an existing page

1. Diff the claimed behavior against current code under `src/mechaharness/`.
2. Update examples to match real CLI flags / API routes / type names.
3. Remove stale backends, harness families, or env vars.
4. Note behavioral changes briefly at the top only when they affect users.

### Sync after code changes

When inference backends, harness families, public types, CLI commands, or API
routes change, update in this order:

1. `docs/reference/` (contract)
2. Related `docs/guides/` examples
3. `docs/architecture.md` if the design shifted
4. `README.md` only for summary/quick-start impact

## Writing rules

- Lead with what the reader can do, then how.
- Use real module paths (`mechaharness.di`, `mechaharness.inference.openai_compat`, etc.).
- Document extension points: `MechaHarnessConfig.get_inference_class` /
  `get_harness_class`, `SettingsConfig.inference_classes()`, subclassing
  `AbstractHarness` / `InferenceStrategy`.
- Call out the separation of concerns explicitly:
  - **Inference Strategy** = provider I/O
  - **Harness hierarchy** = agent loop policy
- Env vars use the `MECHA_` prefix.
- Include the logo with `![MechaHarness](./logo.png)` on `docs/index.md`
  and `![MechaHarness](docs/logo.png)` on `README.md` (path relative to file).
- Do not invent APIs. If unsure, read the code before writing.

## Doc types

| Type | Location | Purpose |
|------|----------|---------|
| Home / TOC | `docs/index.md` | Navigation + project overview |
| Architecture | `docs/architecture.md` | Patterns, layering, extension model |
| Guide | `docs/guides/*.md` | Task-oriented how-tos |
| Reference | `docs/reference/*.md` | Exact CLI/API/types contracts |
| ADR | `docs/adr/NNNN-title.md` | Decision + context + consequences |

## Quality checklist

Before finishing:

- [ ] Facts match current code
- [ ] Code fences use correct language tags
- [ ] Internal links resolve
- [ ] `docs/index.md` lists new/changed pages
- [ ] Logo path is correct for the file's location
- [ ] No secrets or live API keys in examples

## Additional resources

- Page templates: [templates.md](templates.md)
