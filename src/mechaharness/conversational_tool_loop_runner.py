"""Runtime runner that expands ``conversational_tool_loop`` into nested rounds."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.stop_contract import StopContract

CompleteFn = Callable[[list[dict[str, Any]], Mapping[str, Any]], Any]
ToolFn = Callable[[str, Any], Any]
NestedRunFn = Callable[[ExecutionGraph, GraphRunContext, str], Awaitable[Any]]
# Optional MCP / host progress: kwargs include tool_round (1-based) and
# either phase=\"inference\" or tool=<name>.
ProgressFn = Callable[..., None]


class ConversationalToolLoopRunner(GraphNodeRunner):
    """Grow ``tools.subgraph`` as ``round_i → {inference, tool_call*}``.

    ``complete`` returns an assistant-shaped dict with optional ``tool_calls``
    (OpenAI-style). ``dispatch_tool(name, arguments)`` returns a JSON-able
    result. Optional ``nested_run`` executes each round graph with shared
    budget (HF-07 / HF-08 nested observability). Optional ``on_progress``
    reports ``tool_round N / inference`` or ``tool_round N / <tool>``.
    """

    def __init__(
        self,
        *,
        kinds: Sequence[str] | None = None,
        complete: CompleteFn,
        dispatch_tool: ToolFn,
        nested_run: NestedRunFn | None = None,
        on_progress: ProgressFn | None = None,
    ) -> None:
        self._kinds = list(kinds or ["conversational_tool_loop"])
        self._complete = complete
        self._dispatch_tool = dispatch_tool
        self._nested_run = nested_run
        self._on_progress = on_progress

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        max_iterations = int(node.payload.get("max_iterations") or 8)
        stop_raw = node.stop_contract
        if isinstance(stop_raw, dict) and stop_raw.get("max_iterations") is not None:
            max_iterations = int(stop_raw["max_iterations"])
        inference_kind = str(node.payload.get("inference_kind") or "inference")
        tool_call_kind = str(node.payload.get("tool_call_kind") or "tool_call")
        state_key = str(node.payload.get("message_state_key") or "messages")
        raw_messages = node.payload.get(state_key) or []
        messages: list[dict[str, Any]] = (
            list(raw_messages) if isinstance(raw_messages, list) else []
        )

        child = ExecutionGraph(
            id=f"{context.graph.id}:{node.id}",
            goal=f"{node.goal}:rounds",
            version=context.graph.version,
        )
        rounds_ran = 0
        final_text = ""

        for round_i in range(max_iterations):
            rounds_ran = round_i + 1
            round_id = f"round_{round_i}"
            llm_id = f"{round_id}/inference"
            child.add_node(
                GraphNode(
                    id=llm_id,
                    kind=inference_kind,
                    goal="model complete",
                    status=NodeStatus.PENDING,
                    payload={"round": round_i, "phase": "inference"},
                )
            )
            self._emit_progress(tool_round=rounds_ran, phase="inference")
            # Soft dependency edge via depends_on only (no DependencyEdge required
            # for nested manual/nested_run execution).
            assistant = self._complete(messages, {"round": round_i, "node_id": node.id})
            if inspect.isawaitable(assistant):
                assistant = await assistant
            if not isinstance(assistant, dict):
                assistant = {"content": str(assistant), "tool_calls": []}
            messages.append(assistant)
            content = assistant.get("content")
            if isinstance(content, str) and content.strip():
                final_text = content
            llm_node = child.nodes[llm_id]
            llm_node.status = NodeStatus.SUCCEEDED
            llm_node.payload = {
                **llm_node.payload,
                "content": content,
                "tool_calls": assistant.get("tool_calls") or [],
            }

            tool_calls = list(assistant.get("tool_calls") or [])
            if not tool_calls:
                node.subgraph = child.checkpoint()
                if self._nested_run is not None:
                    await self._nested_run(
                        child, context, f"{context.run_id}:{node.id}:r{round_i}"
                    )
                break

            for t_i, call in enumerate(tool_calls):
                fn = call.get("function") or {}
                name = str(fn.get("name") or call.get("name") or f"tool_{t_i}")
                args = fn.get("arguments", call.get("arguments"))
                tc_id = f"{round_id}/tool_call:{name}:{t_i}"
                child.add_node(
                    GraphNode(
                        id=tc_id,
                        kind=tool_call_kind,
                        goal=f"tool {name}",
                        depends_on=[llm_id],
                        status=NodeStatus.PENDING,
                        payload={
                            "round": round_i,
                            "tool_name": name,
                            "arguments": args,
                            "tool_call_id": call.get("id"),
                        },
                    )
                )
                self._emit_progress(tool_round=rounds_ran, tool=name)
                # HF-08: host may pre-attach recipe subgraph on call payload.
                recipe_graph = call.get("subgraph") or call.get("recipe_graph")
                if isinstance(recipe_graph, dict):
                    child.nodes[tc_id].subgraph = recipe_graph
                result = self._dispatch_tool(name, args)
                if inspect.isawaitable(result):
                    result = await result
                child.nodes[tc_id].status = NodeStatus.SUCCEEDED
                child.nodes[tc_id].payload = {
                    **child.nodes[tc_id].payload,
                    "result": result,
                }
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": result
                        if isinstance(result, str)
                        else str(result),
                    }
                )

            node.subgraph = child.checkpoint()
            if self._nested_run is not None:
                await self._nested_run(
                    child, context, f"{context.run_id}:{node.id}:r{round_i}"
                )
        else:
            # Exhausted max_iterations with tools still requested.
            node.subgraph = child.checkpoint()

        node.payload = {
            **node.payload,
            state_key: messages,
            "rounds": rounds_ran,
            "final_text": final_text,
            "child_graph_id": child.id,
        }
        stop = StopContract.model_validate(node.stop_contract) if node.stop_contract else None
        if stop and stop.max_iterations is not None and rounds_ran >= int(stop.max_iterations):
            # Bounded stop — still succeed with interior visible.
            pass
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload=dict(node.payload),
            cost_units=float(rounds_ran),
        )

    def _emit_progress(
        self, *, tool_round: int, phase: str | None = None, tool: str | None = None
    ) -> None:
        if self._on_progress is None:
            return
        if tool is not None:
            self._on_progress(tool_round=tool_round, tool=tool)
        else:
            self._on_progress(tool_round=tool_round, phase=phase or "inference")
