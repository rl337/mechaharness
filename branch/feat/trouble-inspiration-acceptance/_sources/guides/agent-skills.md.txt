# Agent skills for your project

MechaHarness ships **customer-facing** Cursor/Codex-style skills and a short
requirements rule so coding agents in *your* repository use Config DI,
`host_apis`, recipes, and event correlators correctly.

These live in the GitHub tree under [`agent-skills/`](../../agent-skills/)
(not the maintainer skills under `.cursor/skills/`). **Latest published copies
are always on** `main` — prefer raw GitHub URLs so you do not pin a stale
snapshot.

Normative host contract:
[Host integration requirements](../requirements/host-integration.md)
(HOST-01..07).

## What to install

| Skill / rule | Purpose |
|--------------|---------|
| **use-mechaharness** | Config, `host_apis`, recipes, promote matrix |
| **mechaharness-observability** | Event correlators → warehouse / UI joins |
| **mechaharness.mdc** | Compact project rule (globs / always-apply style) |

Browse the directory:

https://github.com/rl337/mechaharness/tree/main/agent-skills

## Latest raw files (`main`)

- use-mechaharness:
  https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/use-mechaharness/SKILL.md
- mechaharness-observability:
  https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/mechaharness-observability/SKILL.md
- requirements rule:
  https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/mechaharness.mdc
- README (install notes):
  https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/README.md

## Copy into Cursor

```bash
mkdir -p .cursor/skills/use-mechaharness \
  .cursor/skills/mechaharness-observability \
  .cursor/rules
curl -fsSL \
  https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/use-mechaharness/SKILL.md \
  -o .cursor/skills/use-mechaharness/SKILL.md
curl -fsSL \
  https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/mechaharness-observability/SKILL.md \
  -o .cursor/skills/mechaharness-observability/SKILL.md
curl -fsSL \
  https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/mechaharness.mdc \
  -o .cursor/rules/mechaharness.mdc
```

Adjust `globs` in `mechaharness.mdc` if your app layout differs.

## Kept in sync by MechaHarness maintainers

When MechaHarness adds or changes public host APIs, Config hooks, recipe
catalog ids, or event correlators, the `agent-skills/` files and this page are
updated in the same change. If you fork or vendor a copy, re-fetch from `main`
periodically so agents see current guidance.

See also [Dependency injection](./dependency-injection.md) and
[Inspiration primitives](../reference/inspiration-primitives.md).
