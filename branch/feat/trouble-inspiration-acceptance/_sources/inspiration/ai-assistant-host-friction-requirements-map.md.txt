# AI assistant project host-friction requirements map

Maps backlog items from
[ai-assistant-host-friction-inspiration.md](./ai-assistant-host-friction-inspiration.md)
(`HF-*`) to modules and user stories.

**Coverage:** *story* means a persona story exercises the path; *surface* means
types exist with unit/doctest coverage; *partial* / *gap* mean incomplete.

| ID | Topic | Modules | Library | Story |
|----|-------|---------|---------|-------|
| HF-01 | Host executor kit | `host_kit.py` | partial | `fangore_host_kit_submit_once` (tap still open → HF-05) |
| HF-02 | Submit-once effectful runner | `host_kit.py` | story | `fangore_host_kit_submit_once` |
| HF-03 | Remote-task recipe promote | — | gap | incubation in host |
| HF-04 | Effectful outcome accessor | `host_kit.effectful_external_handle` | story | `fangore_host_kit_submit_once` |
| HF-05 | Event tap on host entrypoint | `host_kit.host_graph_executor` | story | `fangore_host_kit_event_tap` |
| HF-06 | Subgraph clone-from-checkpoint | — | gap | open |
| HF-07 | Dynamic tool-loop graph | `graph_templates/conversational_tool_loop.py`, `node_component.py` | story | `fangore_conversational_tool_loop`, `fangore_harness_tool_loop_graph` |
| HF-08 | Recipe-as-tool | `node_component` / subgraph nest | story | `fangore_recipe_as_tool` |
| — | Node-component query | `node_component.py` | story | `fangore_node_components` |
| — | Traversal contract | `node_component.py`, `rollout_graph.py` | story | `fangore_traversal_contract` |

Cross-link: observed rollout topology MH-MHRL-03 → `nubble_insp_rollout_graph`.

## Ownership

**MechaHarness owns:** node-component kinds (from existing events/soft points),
query + traversal, host kit tap, `conversational_tool_loop` recipe.

**AI assistant host owns:** console rendering, channel fronts, media backends,
deleting parallel phase mirrors after bind.
