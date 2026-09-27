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

## Conversion sketch

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

## Inline tables (still OK)

Small pure functions may stay as `@pytest.mark.parametrize` without files:

```python
@pytest.mark.parametrize(
    ("attempt", "max_attempts", "expected"),
    [(0, 3, RETRY), (3, 3, ESCALATE), (1, 1, ESCALATE)],
)
def test_default_failure_policy_matrix(attempt, max_attempts, expected): ...
```

Promote to fixture files when rows need nested graphs, grants, or event expects.
