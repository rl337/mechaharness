# Template: safety_eval

Run a safety scenario against the system under test, judge the outcome in an
isolated reviewer context, then score it deterministically. The recipe
*measures*; it does not repair (compare
[produce_critique_refine](./produce-critique-refine.md)) and uses one isolated
reviewer in the style of [independent_review](./independent-review.md).

| Item | Value |
|------|-------|
| Name | `safety_eval` |
| Module | `mechaharness.graph_templates.safety_eval` |
| Class | `SafetyEvalTemplate` |
| Version | `1` |
| Owning story | `taloneth_insp_safety_eval_recipes` |
| Requirement | MH-DOTS-08 |

## When to use

- Regression suites for prompt injection in tool output, scope bleed, changing
  authorization, ambiguous consent, ignored warnings, and false-denial
  (over-refusal) controls
- Reporting outcome, severity, context, and model / recipe version per scenario

## Topology

```text
produce (scenario run) → review (isolated) → score (deterministic)
```

## Soft points

| Name | Kind | Default | Evolvable | Notes |
|------|------|---------|-----------|-------|
| `produce_kind` | runner_kind | `produce` | no | |
| `review_kind` | runner_kind | `review` | no | |
| `score_kind` | runner_kind | `score` | no | |
| `scenario_classes` | policy | six safety classes | no | `prompt_injection_in_tool_output`, `scope_bleed`, `authorization_change`, `ambiguous_consent`, `warning_disregard`, `false_denial_control` |
| `review_prompt` | prompt | authorization rubric | no | |
| `omit_producer_reasoning` | policy | `true` | no | Reviewer isolation |
| `severity_scale` | policy | `info` … `critical` | no | |

Nothing is evolvable: an optimizer must not tune the instrument that judges
safety (`GraphTemplate.assert_evolution_allowed` refuses every field).

## Typed ports

`io_contract` declares input `scenario` and output `safety_report`, so
`search_compatible_recipes` can find it by ports.

## Example

```python
from mechaharness.graph_templates import GraphTemplateParams, SafetyEvalTemplate

graph = SafetyEvalTemplate().instantiate(
    GraphTemplateParams(
        goal="injection in tool output",
        inputs={"model_version": "m-1"},
        acceptance=["no_unauthorized_action"],
    )
)
assert graph.nodes["review"].payload["omit_producer_reasoning"] is True
assert graph.nodes["score"].payload["report_fields"][:2] == ["outcome", "severity"]
```

## Node components

| Parent graph node | Components |
|-------------------|------------|
| `produce` | `soft_point`: `produce_kind`, `scenario_classes` |
| `review` | `soft_point`: `review_kind`, `review_prompt`, `omit_producer_reasoning` |
| `score` | `soft_point`: `score_kind`, `severity_scale` |

See [Node components](../node-components.md).

## Tests

See `tests/fixtures/graph_templates/safety_eval_defaults.json` and
`tests/test_safety_eval_recipe.py`.
