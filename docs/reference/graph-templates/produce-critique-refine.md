# Template: produce_critique_refine

Draft an artifact, critique it in isolated context, then refine under an
explicit stop contract. The critique is judgement text (not a deterministic
oracle) and feeds the refinement loop.

| Item | Value |
|------|-------|
| Name | `produce_critique_refine` |
| Module | `mechaharness.graph_templates.produce_critique_refine` |
| Class | `ProduceCritiqueRefineTemplate` |
| Version | `1` |
| Owning story | `fangore_insp_produce_critique_refine` |

## When to use

- Drafts where an independent critic improves quality but no oracle exists
- When same-context self-critique is too lenient but a full review panel is
  too heavy (compare [independent_review](./independent-review.md) and
  [verify_repair](./verify-repair.md))

## Topology

```text
produce → critique (isolated) → refine (repeating + StopContract) → complete
```

## Soft points

| Name | Kind | Default | Evolvable | Notes |
|------|------|---------|-----------|-------|
| `produce_kind` | runner_kind | `produce` | no | |
| `critique_kind` | runner_kind | `critique` | no | |
| `refine_kind` | runner_kind | `refine` | no | Repeating |
| `complete_kind` | runner_kind | `complete` | no | |
| `critique_prompt` | prompt | critique defects | yes | Voice / strictness of the critic |
| `max_rounds` | budget | `2` | yes | Or `params.stop_contract` |
| `omit_producer_reasoning` | policy | `true` | no | Critic isolation |
| `acceptance` | policy | `[]` | no | On critique/complete |

Only `evolvable` soft points may be rewritten by an optimizer
(`GraphTemplate.assert_evolution_allowed`).

## Example

```python
from mechaharness.graph_templates import (
    GraphTemplateParams,
    ProduceCritiqueRefineTemplate,
)

graph = ProduceCritiqueRefineTemplate().instantiate(
    GraphTemplateParams(
        goal="draft release notes",
        acceptance=["no_unverified_claims"],
        soft_bindings={"max_rounds": 2},
    )
)
assert graph.nodes["critique"].payload["omit_producer_reasoning"] is True
assert graph.nodes["refine"].stop_contract["max_iterations"] == 2
```

## Node components

| Parent graph node | Components |
|-------------------|------------|
| `produce` | `soft_point`: `produce_kind` |
| `critique` | `soft_point`: `critique_kind`, `critique_prompt`, `omit_producer_reasoning`, `acceptance` |
| `refine` | `stop_contract` (repeating), `soft_point`: `refine_kind`, `max_rounds` |
| `complete` | `soft_point`: `complete_kind` |

See [Node components](../node-components.md).

## Tests

See `tests/fixtures/graph_templates/produce_critique_refine_*.json` and
`tests/test_produce_critique_refine_recipe.py`.
