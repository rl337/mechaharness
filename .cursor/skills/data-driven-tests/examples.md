# Data-driven tests — examples

## Reference implementation

| Piece | Path |
|-------|------|
| Fixtures | `tests/fixtures/graph_executor/*.json` |
| Interpreter | `tests/support/graph_executor_cases.py` |
| Parametrize | `tests/test_graph_executor.py` |

### Minimal fixture

```json
{
  "id": "deny_missing_execute_grant",
  "description": "Executor refuses to start without core:graph.execute",
  "grants": [],
  "failure_policy": "default",
  "escalation": "reject",
  "runners": { "noop": { "mode": "succeed" } },
  "graph": {
    "goal": "denied",
    "nodes": [{ "id": "a", "kind": "noop", "max_attempts": 2 }]
  },
  "run": { "run_id": "deny" },
  "expect": {
    "status": "denied",
    "error": "missing_grant:core:graph.execute",
    "nodes": { "a": { "status": "pending", "attempt": 0 } },
    "events_include": ["core:graph_start", "core:graph_end"],
    "runner_calls": { "noop": 0 }
  }
}
```

### Multi-phase (resume)

Use `phases` when a later run depends on a checkpoint mutation:

```json
{
  "id": "resume_skips_succeeded_upstream",
  "grants": ["core:graph.execute"],
  "runners": { "step": { "mode": "echo_id" } },
  "graph": { "nodes": [/* … */], "edges": [/* … */] },
  "phases": [
    {
      "run": { "run_id": "resume-1" },
      "expect": { "status": "ok", "run_order": ["a", "b"] }
    },
    {
      "mutate": { "nodes": { "b": { "status": "pending", "attempt": 0, "clear_payload": true } } },
      "run": { "run_id": "resume-1", "resume": true },
      "expect": { "status": "ok", "run_order": ["b"], "runner_calls": { "step": 1 } }
    }
  ]
}
```

Delta call logs per phase in the test loop so phase-2 expects stay local.

## Conversion sketch — JSON tier

**Before** (proliferation):

```python
async def test_executor_denies_without_grant(): ...
async def test_node_runner_grants_enforced(): ...
async def test_failure_policy_fail_stops_node(): ...
```

**After**:

1. `tests/support/<domain>_cases.py` — `build_*`, `assert_expect`, `iter_cases`
2. One JSON per former test body
3. Single `test_<domain>_case` parametrize
4. Keep `test_registry_rejects_duplicate_kind` as a structural unit test

## Conversion sketch — struct tier

**Before**:

```python
def test_simple_http_joins_base_and_path(): ...
def test_full_url_override(): ...
def test_custom_path(): ...
```

**After** (no `tests/fixtures/` needed):

```python
@dataclass(frozen=True)
class _EndpointCase:
    id: str
    kwargs: dict
    endpoint: str


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.id)
def test_endpoint_url_from_fields(case: _EndpointCase) -> None:
    assert SimpleHttpConnectionConfig(**case.kwargs).endpoint_url() == case.endpoint
```

Same idea for policy/allowlist/error matrices — see `tests/test_access.py`,
`tests/test_api_connection.py`, `tests/test_tool_phase.py`.

## Inline tables (struct tier)

Small pure functions stay as `@pytest.mark.parametrize` without files:

```python
@pytest.mark.parametrize(
    ("attempt", "max_attempts", "expected"),
    [(0, 3, RETRY), (3, 3, ESCALATE), (1, 1, ESCALATE)],
)
def test_default_failure_policy_matrix(attempt, max_attempts, expected): ...
```

Promote to fixture files when rows need nested graphs, grants, or event expects.
