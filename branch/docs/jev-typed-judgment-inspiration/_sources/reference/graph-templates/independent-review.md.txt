# Template: independent_review

Isolated reviewers see the artifact and acceptance contract, not producer
reasoning (by default). Aggregation retains disagreement.

| Item | Value |
|------|-------|
| Name | `independent_review` |
| Module | `mechaharness.graph_templates.independent_review` |
| Class | `IndependentReviewTemplate` |
| Version | `1` |

## When to use

- Adversarial or second-opinion checks
- Migrations / high-consequence edits needing independent eyes
- When same-context “please reconsider” is insufficient

## Topology

```text
produce → review_0 … review_N → aggregate_reviews
```

## Soft points

| Name | Kind | Default | Notes |
|------|------|---------|-------|
| `produce_kind` | runner_kind | `produce` | |
| `review_kind` | runner_kind | `review` | |
| `aggregate_kind` | runner_kind | `aggregate_reviews` | |
| `reviewer_count` | budget | `1` | |
| `omit_producer_reasoning` | policy | `true` | |
| `acceptance` | policy | `[]` | Passed into review payloads |

## Example

```python
from mechaharness.graph_templates import (
    GraphTemplateParams,
    IndependentReviewTemplate,
)

graph = IndependentReviewTemplate().instantiate(
    GraphTemplateParams(
        goal="review migration plan",
        inputs={"reviewer_count": 2},
        acceptance=["lgtm"],
        soft_bindings={"omit_producer_reasoning": True},
    )
)
assert graph.nodes["review_0"].payload["isolated_context"] is True
assert graph.nodes["aggregate_reviews"].payload["retain_disagreement"] is True
```

## Tests

See `tests/fixtures/graph_templates/independent_review_*.json`.
