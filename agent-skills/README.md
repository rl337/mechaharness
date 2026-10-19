# Agent skills for apps using MechaHarness

Recommended Cursor/Codex-style skills and a short requirements rule so coding
agents in **your** repository wire MechaHarness correctly (Config DI,
`host_apis`, recipes, event correlators).

These files are **for downstream projects**, not for developing MechaHarness
itself (maintainer skills live under `.cursor/skills/`).

**Maintainer requirement:** when public host APIs, Config hooks, recipe
catalog ids, or event correlators change, update these skills (and
`docs/guides/agent-skills.md`) in the **same** change. Stale consumer skills
are treated as a docs/product bug — see `.cursor/skills/project-docs/SKILL.md`.

## Contents

| Path | Purpose |
| --- | --- |
| [`use-mechaharness/SKILL.md`](use-mechaharness/SKILL.md) | Config, `host_apis`, recipes, promote matrix |
| [`mechaharness-observability/SKILL.md`](mechaharness-observability/SKILL.md) | Event correlators → warehouse / UI joins |
| [`mechaharness.mdc`](mechaharness.mdc) | Compact always-on-style requirements rule |

## Install into your project

**Cursor skills** — copy a skill directory into `.cursor/skills/`:

```bash
mkdir -p .cursor/skills
curl -fsSL \
  https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/use-mechaharness/SKILL.md \
  -o .cursor/skills/use-mechaharness/SKILL.md --create-dirs
```

Or clone sparingly:

```bash
git clone --depth 1 https://github.com/rl337/mechaharness.git /tmp/mechaharness
cp -R /tmp/mechaharness/agent-skills/use-mechaharness .cursor/skills/
cp -R /tmp/mechaharness/agent-skills/mechaharness-observability .cursor/skills/
cp /tmp/mechaharness/agent-skills/mechaharness.mdc .cursor/rules/
```

**Cursor rules** — copy `mechaharness.mdc` into `.cursor/rules/` and adjust
`globs` if needed.

Prefer **raw URLs on `main`** so agents always fetch the latest published guidance.

## Latest on GitHub

- Browse: https://github.com/rl337/mechaharness/tree/main/agent-skills
- use-mechaharness (raw): https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/use-mechaharness/SKILL.md
- mechaharness-observability (raw): https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/mechaharness-observability/SKILL.md
- mechaharness.mdc (raw): https://raw.githubusercontent.com/rl337/mechaharness/main/agent-skills/mechaharness.mdc

Docs: https://rl337.org/mechaharness/guides/agent-skills.html
(source: `docs/guides/agent-skills.md`)
