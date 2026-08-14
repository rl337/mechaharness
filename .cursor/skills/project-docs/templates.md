# Documentation templates

Copy the matching template when creating a new page. Replace bracketed placeholders.

## Guide (`docs/guides/<topic>.md`)

```markdown
# [Guide title]

[One sentence: what the reader will accomplish.]

## Prerequisites

- [Requirement]

## Steps

1. [Action]
2. [Action]

```bash
# example command
```

## Verify

[How to confirm it worked.]

## Next

- [Related guide or reference]
```

## Reference (`docs/reference/<topic>.md`)

```markdown
# [Reference title]

[One sentence: what contract this documents.]

## Surface

| Item | Value |
|------|-------|
| Module / entrypoint | `[path]` |
| Stability | stable / evolving |

## Details

### [Symbol or command]

[Exact behavior, parameters, examples.]

## Examples

```bash
# or python
```
```

## Architecture section addition

When extending `docs/architecture.md`, add a short subsection:

```markdown
## [Concern name]

**Pattern:** [Strategy | Template method | Registry | …]

**Code:** `[module.path]`

[2–4 sentences on responsibility and non-goals.]
```

## ADR (`docs/adr/NNNN-title.md`)

```markdown
# NNNN. [Title]

- Status: Proposed | Accepted | Superseded
- Date: YYYY-MM-DD

## Context

[Problem and forces.]

## Decision

[What we chose.]

## Consequences

- [Positive]
- [Negative / trade-off]
```
