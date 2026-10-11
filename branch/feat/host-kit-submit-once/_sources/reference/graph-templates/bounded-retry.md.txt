# Bounded retry (`bounded_retry`)

**Agentic Recipe.** Make retry visible: attempt, classify failure, permit retry
in code, apply backoff, and escalate when exhausted. Attempt nodes declare
effect-reconciliation requirements so durable resume is not bypassed.

| Surface | Value |
|---------|-------|
| Catalog id | `bounded_retry` |
| Module | `mechaharness.graph_templates.bounded_retry` |
| Substrate | `GraphTemplate` |
| Owning stories | `fangore_bounded_retry_recipe` |

## When to use

- Retries that need classification, remediation, and an explicit terminal edge
- Dispatch paths that must compose with durable external-effect recovery

Do not use infinite implicit executor retry as a substitute for this recipe when
the control flow must be observable.

## Soft points

| Name | Kind | Role |
|------|------|------|
| `attempt_kind` | runner_kind | Work / dispatch per attempt |
| `classify_kind` | runner_kind | Failure classification |
| `permit_kind` | runner_kind | Deterministic retry permission |
| `backoff_kind` | runner_kind | Remediation / backoff |
| `escalate_kind` | runner_kind | Terminal escalation |
| `stop_contract` / `max_attempts` | budget | Bound repeating attempts |
| `failure_classifier` | policy | Soft point for ambiguous failures |

## Tiling example

```python
from mechaharness.graph_templates import (
    BoundedRetryTemplate,
    GraphTemplateParams,
)

graph = BoundedRetryTemplate().instantiate(
    GraphTemplateParams(
        goal="dispatch remote job with safe retry",
        inputs={"max_attempts": 3},
    )
)
assert graph.nodes["attempt"].payload["requires_effect_reconciliation"] is True
```

## Related

- [Graph templates and Agentic Recipes](../graph-templates.md)
- [Recipes requirements](../../requirements/recipes-and-decision-plane.md)
- [Transactional durable resume](../../requirements/transactional-durable-resume.md)
