---
name: data-driven-tests
description: >-
  Write and convert MechaHarness tests as case matrices — either lightweight
  loops over frozen structs / @parametrize rows, or declarative JSON fixtures —
  so coverage grows without proliferating near-duplicate test functions. Use
  when adding tests, expanding coverage, parametrizing cases, converting
  existing unit tests to table-driven or fixture-driven form, testing Agentic
  Recipe expansion matrices, scanning for clone test_* functions, or when the
  user mentions fixtures, case matrices, table-driven tests, struct loops, or
  test proliferation.
---

# Data-driven tests

Prefer **one interpreter + many cases** over N pytest functions that each
rebuild the same arrange/act/assert with slight input tweaks. Cases state
*outcomes*; the harness must not copy-paste production control flow.

There are **two tiers**. Prefer the lightest that fits:

| Tier | Form | When |
|------|------|------|
| **Struct / parametrize** | Frozen dataclass (or tuple) rows + one `@pytest.mark.parametrize` | Same setup/teardown shape; deltas are fields and expects; no nested graphs/scripts |
| **JSON fixtures** | `tests/fixtures/<domain>/*.json` + `tests/support/<domain>_cases.py` | Nested arrange data, shared builders, multi-phase, or many cases that should be editable without touching Python |

Canonical JSON example: `tests/fixtures/graph_executor/*.json` +
`tests/support/graph_executor_cases.py` + `tests/test_graph_executor.py`.

Canonical struct examples: `tests/test_api_connection.py`, grant/policy matrices
in `tests/test_access.py`, phase×effect in `tests/test_tool_phase.py`.

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
- Async scripts diverge so much that a shared loop would hide the story
  (named tests with shared helpers are fine)

## Choose the tier

```text
Same arrange/act/assert, differ by a few fields?
  └─ yes → Struct / @parametrize in the test module (or tiny helper)
       └─ rows growing nested / multi-phase / many files?
            └─ yes → Promote to JSON fixtures + support interpreter
  └─ no → Leave as a named unit test
```

**Promote to JSON** when rows need nested graphs, grants lists, event expects,
script modes, or resume phases. **Stay on structs** when a frozen dataclass
(or a short tuple table) stays readable in one screen and needs no
`tests/support/` builder.

## Identifying candidates (scan)

When asked to find tests to data-drive — not only JSON matrices — **scan for
near-clones first**, then pick the lightest tier:

```text
Scan task:
- [ ] 1. List test modules (user path, git diff, or tests/)
- [ ] 2. Cluster test_* that share arrange/act and differ by data
- [ ] 3. For each cluster, choose struct loop vs JSON fixtures (see Choose the tier)
- [ ] 4. Skip uniques: DI wiring, import smoke, one-off structural invariants
- [ ] 5. Skip already-good matrices (existing @parametrize / fixtures)
- [ ] 6. Propose conversions; convert strongest clusters; leave the rest alone
```

### Clone smells (struct loop is often enough)

| Smell | Prefer |
|-------|--------|
| 2–N tests that only change kwargs / expected string / bool | `@parametrize` over structs or tuples |
| Parallel tests that assert the free function *and* a registry with the same matrix | One loop covering both surfaces |
| Error-path tests that only change `raises(…, match=…)` | Error-case struct table |
| Policy / allowlist / filter matrices as separate functions | One `allows` / `query` / `assert_evolution` parametrize |
| 3+ tests with same harness/DI bootstrap and nested expect | JSON fixtures + support interpreter |
| Asserts only on status/error/payload keys with rich arrange | JSON `expect` |
| One test documents a unique invariant | Leave named |
| Story harness already covers acceptance | Do not duplicate story prose |

## Workflow (struct / parametrize)

Copy and track:

```text
Struct-matrix task:
- [ ] 1. Name the cluster (what varies: endpoint, grant, phase×effect, …)
- [ ] 2. Define a frozen dataclass (or keep a short tuple table if ≤3 fields)
- [ ] 3. List rows with stable ids=…
- [ ] 4. One test_* that builds once per row and asserts from the struct
- [ ] 5. Merge parallel surfaces that share the matrix (function + registry)
- [ ] 6. Leave true one-offs as named tests beside the matrix
- [ ] 7. Run the module; do not add per-id branches inside the loop
```

### Struct pattern

```python
@dataclass(frozen=True)
class _EndpointCase:
    id: str
    kwargs: dict
    endpoint: str
    model: str | None = None


_CASES = [
    _EndpointCase("joins_base_and_path", {...}, "http://…"),
    ...
]


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.id)
def test_endpoint_url_from_fields(case: _EndpointCase) -> None:
    conn = SimpleHttpConnectionConfig(**case.kwargs)
    assert conn.endpoint_url() == case.endpoint
```

Tuple tables are fine when columns are obvious:

```python
@pytest.mark.parametrize(
    ("grants", "required", "allowed"),
    [
        ([], [FsWrite], False),
        ([FsWrite, WidgetGrant], [FsWrite], True),
    ],
    ids=["deny_by_default", "subset_of_grants"],
)
def test_access_policy_allows(grants, required, allowed) -> None:
    assert AccessPolicy(grants=grants).allows(required) is allowed
```

## Workflow (JSON fixtures — new coverage)

Copy and track:

```text
Fixture-matrix task:
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
   and constructor guards (struct `@parametrize` tables are the right home for
   those pure matrices).

### Parametrize pattern (fixtures)

```python
_CASES = iter_cases()

@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.id)
async def test_<domain>_case(case: Case) -> None:
    ...
```

Guard: `assert len(_CASES) >= N` and unique ids.

## Workflow (convert existing tests)

When asked to increase coverage or reduce duplication, **scan then convert**
(struct first, JSON when the cluster outgrows inline rows):

```text
Convert task:
- [ ] 1. List candidate test modules (user path or git diff / tests/)
- [ ] 2. Cluster tests that share arrange/act and differ by data
- [ ] 3. Choose tier per cluster (struct loop vs JSON fixtures)
- [ ] 4. Propose which tests stay as structural / named unit tests
- [ ] 5a. Struct: extract rows + one parametrize; delete clone bodies
- [ ] 5b. JSON: extract builder into tests/support/<domain>_cases.py; one fixture per former body
- [ ] 6. Run old module path; confirm same behaviors, fewer functions
- [ ] 7. Add any missing matrix cells discovered while clustering
```

### User stories share the same interpreter philosophy

Persona **user stories** (`tests/fixtures/models/…/stories/`) keep narrative /
persona fields, but **execution** is harness-driven: `story.json` `kind` is a
harness family; `request.op` selects the surface. Do **not** add a new kind per
story — see [`user-stories`](../user-stories/SKILL.md). Unit fixture matrices
(`tests/fixtures/<domain>/`) and inline struct tables remain for non-persona
branch coverage.

### What not to convert

- Live/cassette HTTP tests whose value is the wire recording.
- Tests whose failure message must point at a specific line of production code
  for debugging a known bug (keep until fixed, then consider matrix).
- Mixed integration tests where each case needs a different script shape.

## Anti-patterns

```python
# BAD — N clones
async def test_deny_without_grant(): ...
async def test_deny_without_escalate(): ...
async def test_deny_without_fs_write(): ...

# BAD — JSON fixtures for a 3-field pure matrix (overkill)
# GOOD — frozen dataclass / tuple @parametrize in the unit module

# BAD — parametrize of giant inline dicts that re-implement the executor
@pytest.mark.parametrize("case", [ { ...50 lines...}, ...])
# GOOD — promote those rows to tests/fixtures/<domain>/

# BAD — fixture or struct id switches inside the test
if case.id == "resume":
    special_resume_logic()

# GOOD — fixtures on disk + one interpreter (or structs with fields that drive asserts)
result = await executor.run(graph, ...)
assert_expect(result=result, expect=case.expect, ...)
```

## Checklist before finishing

- [ ] New cases are rows (structs) or files under `tests/fixtures/<domain>/`, not
      new near-clone `test_*` functions
- [ ] Tier matches complexity (structs for flat matrices; JSON for nested/multi-phase)
- [ ] Support module name matches domain (JSON tier only)
- [ ] Interpreter / loop has no per-case id branches
- [ ] Structural tests remain only where a matrix would obscure intent
- [ ] `pytest tests/test_<domain>.py` green
- [ ] If acceptance behavior changed, update the owning user story `validation`

## Additional resources

- Example matrix: [examples.md](examples.md)
- Naming: `.cursor/rules/unambiguous-names.mdc`
- Stories (harness + narrative): `.cursor/skills/user-stories/SKILL.md`
- Story harness registry: `tests/stories/harness/`
