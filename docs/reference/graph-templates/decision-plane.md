# Typed decision plane (`decision_plane`)

**Agentic Recipe.** Project structured state, ask a batch of bounded questions
in one inference step, keep deterministic facts in code, apply final policy in
code, and escalate when confidence is too low.

| Surface | Value |
|---------|-------|
| Catalog id | `decision_plane` |
| Module | `mechaharness.graph_templates.decision_plane` |
| Substrate | `GraphTemplate` |
| Owning stories | `fangore_decision_plane_recipe` |

## When to use

- High-volume, well-defined decisions with enumerable actions
- Moving routine triage off a frontier model while keeping policy in code

Do not use when the model must invent open-ended commands with no action envelope.

## Soft points

| Name | Kind | Role |
|------|------|------|
| `project_kind` | runner_kind | Builds the deliberate state projection |
| `ask_kind` | runner_kind | One batched decision inference call |
| `policy_kind` | runner_kind | Deterministic final policy |
| `escalate_kind` | runner_kind | Routable escalation exit |
| `shadow_ask_kind` | runner_kind | Non-gating shadow path |
| `confidence_floor` | policy | Minimum confidence before accept |
| `shadow_mode` | policy | Add shadow ask without gating execution |
| `questions` / `state_projection` / `facts` | task_state | Via `params.inputs` or soft bindings |

## Tiling example

```python
from mechaharness.graph_templates import (
    DecisionPlaneTemplate,
    GraphTemplateParams,
)

graph = DecisionPlaneTemplate().instantiate(
    GraphTemplateParams(
        goal="route refund triage",
        inputs={
            "state_projection": {"ticket_id": "T-1"},
            "facts": {"duplicate_charge": True},
            "questions": [
                {
                    "id": "team",
                    "kind": "choice",
                    "options": ["billing", "technical"],
                    "allowed_actions": ["billing", "technical"],
                },
                {"id": "risk", "kind": "score", "min": 0, "max": 1},
            ],
            "confidence_floor": 0.7,
            "shadow_mode": True,
        },
    )
)
assert graph.template_name == "decision_plane"
```

## Related

- [Graph templates and Agentic Recipes](../graph-templates.md)
- [Recipes requirements](../../requirements/recipes-and-decision-plane.md)
