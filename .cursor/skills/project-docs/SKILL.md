---
name: project-docs
description: >-
  Create and maintain MechaHarness project documentation under docs/.
  Use when writing, updating, restructuring, or reviewing docs; when the user
  mentions documentation, docs/, README sync, architecture notes, guides,
  Agentic Recipes / graph templates, requirements under docs/requirements/, or
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
  architecture.md       # Design: Strategy + harness + recipes
  guides/               # How-to guides (install, local models, extend, agent-skills)
  reference/            # Stable contracts (types, CLI, HTTP API, recipes)
  requirements/         # Normative library + host-integration requirements
  inspiration/          # Attribution / gap analysis (not specification)
  adr/                  # Architecture Decision Records (optional)

agent-skills/           # Customer-facing skills for *apps using* MechaHarness
  use-mechaharness/
  mechaharness-observability/
  mechaharness.mdc
```

Keep `README.md` short: logo, one-line pitch, install/quick start, and links
into `docs/`. Do not duplicate long reference material in the README.

| Audience | Location | Notes |
|----------|----------|-------|
| Maintainer agents | `.cursor/skills/` | Developing *this* repo |
| Downstream / host agents | `agent-skills/` + `docs/guides/agent-skills.md` | Copy into *their* `.cursor/skills/`; keep in sync when public host APIs change |

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

When inference backends, harness families, public types, CLI commands, API
routes, or Agentic Recipes / graph templates change, update in this order:

1. `docs/reference/` (contract) — recipe pages under `reference/graph-templates/`
2. Related `docs/guides/` examples
3. `docs/architecture.md` if the design shifted
4. `docs/requirements/` when normative MUST/SHOULD text changes
5. **Customer-facing `agent-skills/`** when `host_apis`, Config hooks, promote
   guidance, recipe catalog ids, or event correlators change — plus
   `docs/guides/agent-skills.md` and `docs/requirements/host-integration.md`
6. `README.md` only for summary/quick-start impact

Stale downstream skills are a docs/product bug (same bar as pyiv
`agent-skills/`).

**Agentic Recipes** are a top-level concept (substrate: `GraphTemplate`). Treat
recipe catalog docs as first-class reference pages: catalog id, when to use,
readable tiling example, soft points, **Node components** subsection (kinds
from [`docs/reference/node-components.md`](../../../docs/reference/node-components.md)),
owning user-story id(s). Follow [`agentic-recipes`](../agentic-recipes/SKILL.md)
and [`node-components`](../node-components/SKILL.md).

When the change is **user-facing acceptance behavior** (harness runs, grants,
lanes, judge/verdicts, adapters, recipes), defer entirely to the
[`user-stories`](../user-stories/SKILL.md) skill: edit `story.json` +
`scenarios/*.yaml` (`kind: cli`; all stories are migrating off legacy `op`
fixtures), keep twin copies identical, regenerate
`docs/guides/user-stories.md` with `scripts/generate_user_stories_md.py`, and
run `--check`. Do **not** hand-edit the user-stories guide as ordinary markdown.

## Writing rules

- Lead with what the reader can do, then how.
- Use real module paths (`mechaharness.di`, `mechaharness.inference.openai_compat`, etc.).
- Document extension points: `MechaHarnessConfig.get_inference_class` /
  `get_harness_class`, `SettingsConfig.inference_classes()`, subclassing
  `AbstractHarness` / `InferenceStrategy`.
- When documenting DI wiring, show **Config `configure()` bind + constructor
  / `inject(T)` consume**. Do not teach `getattr(self, "_x", None)` caches or
  hooks that call sibling `get_*` for collaborators; point at
  `docs/requirements/dependency-injection.md` and the `di-config-ownership`
  skill.
- Call out the separation of concerns explicitly:
  - **Inference Strategy** = provider I/O
  - **Harness hierarchy** = agent loop policy
  - **Agentic Recipes** = reusable control subgraphs (`GraphTemplate` substrate)
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
| Reference | `docs/reference/*.md` | Exact CLI/API/types/recipe contracts |
| Requirements | `docs/requirements/*.md` | Normative library + host-integration requirements |
| Downstream skills | `agent-skills/` | Customer Cursor skills / `mechaharness.mdc` for host apps |
| Inspiration | `docs/inspiration/*.md` | Attribution / gaps (not specification) |
| ADR | `docs/adr/NNNN-title.md` (local-only / gitignored) | Decision + context + consequences |

## Quality checklist

Before finishing:

- [ ] Facts match current code
- [ ] Code fences use correct language tags
- [ ] Internal links resolve
- [ ] `docs/index.md` lists new/changed pages
- [ ] Logo path is correct for the file's location
- [ ] No secrets or live API keys in examples
- [ ] If host-facing APIs changed: `agent-skills/` + guide + HOST requirements match

## Additional resources

- Page templates: [templates.md](templates.md)
- Agentic Recipes: [`agentic-recipes`](../agentic-recipes/SKILL.md)
- User stories: [`user-stories`](../user-stories/SKILL.md)
- Event observability: [`event-observability`](../event-observability/SKILL.md)
- Downstream consumers: [`../../agent-skills/`](../../agent-skills/),
  [`docs/guides/agent-skills.md`](../../../docs/guides/agent-skills.md)
