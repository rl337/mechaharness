# Conversational tool loop (`conversational_tool_loop`)

**Agentic Recipe.** Bound tool loop whose runtime expands nested
`inference` / `tool_call` graph nodes under a `tools` parent without
pre-unrolling max iterations. Node components use existing kinds only.

| Surface | Value |
|---------|-------|
| Catalog id | `conversational_tool_loop` |
| Module | `mechaharness.graph_templates.conversational_tool_loop` |
| Runner | `mechaharness.conversational_tool_loop_runner.ConversationalToolLoopRunner` |
| Substrate | `GraphTemplate` |
| Owning stories | `fangore_conversational_tool_loop` |

## When to use

- Host chat / agent turns that need zoomable tool back-and-forths
- Replacing opaque in-node tool loops with checkpointed interiors

## Soft points

| Name | Kind | Role |
|------|------|------|
| `tools_kind` | runner_kind | Controller node kind |
| `inference_kind` | runner_kind | Model complete step |
| `tool_call_kind` | runner_kind | Per-tool invocation |
| `stop_contract` / `max_iterations` | budget | Bound rounds |
| `message_state_key` | task_state | Carried messages |
| `tool_dispatch` | tool | Host dispatch bind |
| `inference` | provider | Host complete bind |

## Node components

| Parent graph node | Components |
|-------------------|------------|
| `tools` | `stop_contract`, `soft_point` (template slots), planned `inference` / `tool_call` when tool names bound; runtime nest grows nested graph nodes for rounds |

See [Node components](../node-components.md).

## Tiling example

```python
from mechaharness.conversational_tool_loop_runner import ConversationalToolLoopRunner
from mechaharness.graph_templates import (
    ConversationalToolLoopTemplate,
    GraphTemplateParams,
)
from mechaharness.host_kit import host_graph_executor

graph = ConversationalToolLoopTemplate().instantiate(
    GraphTemplateParams(goal="chat tools", inputs={"max_iterations": 4})
)
runner = ConversationalToolLoopRunner(
    complete=lambda messages, meta: {"role": "assistant", "content": "hi", "tool_calls": []},
    dispatch_tool=lambda name, args: "ok",
)
executor = host_graph_executor(runners=[runner])
```

## Related

- HF-08: `embed_recipe_as_tool` in `mechaharness.node_component`
- Requirements: [dynamic-tool-graph.md](../../requirements/dynamic-tool-graph.md)
