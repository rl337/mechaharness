---
name: data-driven-tests
description: >-
  Write and convert MechaHarness tests as declarative fixture matrices so
  coverage grows without proliferating near-duplicate test functions. Use when
  adding tests, expanding coverage, parametrizing cases, converting existing
  unit tests to data-driven form, testing Agentic Recipe expansion matrices, or
  when the user mentions fixtures, case matrices, table-driven tests, or test
  proliferation.
---

# Data-driven tests

Prefer **one interpreter + many fixtures** over N pytest functions that each
rebuild the same arrange/act/assert with slight input tweaks. Fixtures state
*outcomes*; the harness must not copy-paste production control flow.

Canonical example: `tests/fixtures/graph_executor/*.json` +
`tests/support/graph_executor_cases.py` + `tests/test_graph_executor.py`.

Respect `.cursor/rules/unambiguous-names.mdc`: fixture dirs and support modules
name the domain (`graph_executor`, `graph_templates`, recipe catalog ids — not
`cases` / `matrix`).

Agentic Recipe expansion, decision-batching, confidence escalation, and retry
boundary matrices belong under domain-clear fixture paths (for example
`tests/fixtures/graph_templates/`) and still need an owning user story per
[`agentic-recipes`](../agentic-recipes/SKILL.md).

## When to apply

**Do** data-drive when:

- Several tests share setup and differ mainly by inputs / expected status
- You are covering a decision matrix (grants, policies, retries, statuses)
- New coverage would otherwise add another near-clone `test_*` function
- Soft expects already look like JSON (stories, policy tables)

**Do not** force it when:

- The test is a unique structural check (API shape, DI wiring, import smoke)
- Setup is one-off and a fixture DSL would be longer than the test
- Asserts need rich call-graph inspection that fixtures cannot express yet
  (keep one focused unit test; optionally add a fixture mode later)

## Workflow (new coverage)

Copy and track:

```text
Data-driven task:
- [ ] 1. Name the domain (fixture dir + support module + test module)
- [ ] 2. Sketch the case schema (inputs, scripts, expect keys)
- [ ] 3. Implement / extend the interpreter in tests/support/
- [ ] 4. Add fixtures under tests/fixtures/<domain>/
- [ ] 5. Parametrize one test_* over iter_cases(); keep tiny structural tests aside
- [ ] 6. Assert matrix size / unique ids so empty dirs fail loudly
- [ ] 7. Run the module; fix interpreter bugs, not case-by-case forks
```

### Layout

```text
tests/
  fixtures/<domain>/           # one *.json (or yaml) per case; id == stem preferred
  support/<domain>_cases.py    # load, build doubles, assert_expect
  test_<domain>.py             # @pytest.mark.parametrize over iter_cases()
```

Mirror source concepts: `graph_executor` → `test_graph_executor.py`, not
`test_cases.py`.

### Case shape (minimum)

Each fixture is a JSON object:

| Field | Role |
|-------|------|
| `id` | Stable case id (default: filename stem) |
| `description` | Why this case exists (human / review) |
| inputs… | Domain-specific arrange data |
| `expect` | Soft or exact outcomes the interpreter understands |

Prefer **script modes** (`succeed`, `fail_n_then_succeed`, `raise`) over embedding
Python in JSON. Put branching in the support interpreter once.

### Interpreter rules

1. **Dumb about production internals** — build public types; call the public API;
   assert on results/events/payloads.
2. **One assert helper** — `assert_expect(result, expect, …)` with clear
   `case {id}: …` messages.
3. **Phases only when needed** — multi-step resume/mutate via `phases[]`; reset
   or delta call logs per phase.
4. **No case-specific `if case.id == …`** in the test module — that is
   proliferation in disguise. Extend the schema/interpreter instead.
5. **Keep structural unit tests** for registry validation, pure policy tables,
   and constructor guards (small `@parametrize` tables are fine inline).

### Parametrize pattern

```python
_CASES = iter_cases()

@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.id)
async def test_<domain>_case(case: Case) -> None:
    ...
```

Guard: `assert len(_CASES) >= N` and unique ids.

## Workflow (convert existing tests)

When asked to increase coverage or reduce duplication, **scan then convert**:

```text
Convert task:
- [ ] 1. List candidate test modules (user path or git diff / tests/)
- [ ] 2. Cluster tests that share arrange/act and differ by data
- [ ] 3. Propose schema + which tests stay as structural unit tests
- [ ] 4. Extract shared builder into tests/support/<domain>_cases.py
- [ ] 5. Move each cluster member into a fixture; delete the old test body
- [ ] 6. Run old module path; confirm same behaviors, fewer functions
- [ ] 7. Add any missing matrix cells discovered while clustering
```

### Conversion heuristics

| Smell | Action |
|-------|--------|
| 3+ tests with same harness/DI bootstrap | Extract Config/builder; fixture the deltas |
| Asserts only on status/error/payload keys | Map 1:1 into `expect` |
| Copy-pasted async `run()` with different grants | Fixture `grants` + shared executor build |
| One test documents a unique invariant | Leave as a named unit test |
| Story runner already covers acceptance | Do not duplicate story prose; unit matrix for branch coverage |

### What not to convert

- Persona **user stories** (`tests/fixtures/models/…/stories/`) — different
  system; see `user-stories` skill.
- Live/cassette HTTP tests whose value is the wire recording.
- Tests whose failure message must point at a specific line of production code
  for debugging a known bug (keep until fixed, then consider matrix).

## Anti-patterns

```python
# BAD — N clones
async def test_deny_without_grant(): ...
async def test_deny_without_escalate(): ...
async def test_deny_without_fs_write(): ...

# BAD — parametrize of giant inline dicts that re-implement the executor
@pytest.mark.parametrize("case", [ { ...50 lines...}, ...])

# BAD — fixture id switches inside the test
if case.id == "resume":
    special_resume_logic()

# GOOD — fixtures on disk + one interpreter
result = await executor.run(graph, ...)
assert_expect(result=result, expect=case.expect, ...)
```

## Checklist before finishing

- [ ] New cases are files under `tests/fixtures/<domain>/`, not new test functions
- [ ] Support module name matches domain
- [ ] Interpreter has no per-case id branches
- [ ] Structural tests remain only where fixtures would obscure intent
- [ ] `pytest tests/test_<domain>.py` green
- [ ] If acceptance behavior changed, update the owning user story `validation`

## Additional resources

- Example matrix: [examples.md](examples.md)
- Naming: `.cursor/rules/unambiguous-names.mdc`
- Stories (separate): `.cursor/skills/user-stories/SKILL.md`
