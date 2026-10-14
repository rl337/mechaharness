"""Conversational tool-loop Agentic Recipe (HF-07).

Binds a parent ``tools`` graph node whose runtime expands nested rounds
(``inference`` / ``tool_call``) without pre-unrolling max iterations.
"""

from __future__ import annotations

from mechaharness.graph import ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)
from mechaharness.stop_contract import StopContract


class ConversationalToolLoopTemplate(GraphTemplate):
    """Bounded tool loop as an expandable ExecutionGraph under ``tools``.

    Runtime (:class:`~mechaharness.conversational_tool_loop_runner.ConversationalToolLoopRunner`)
    grows nested ``inference`` / ``tool_call`` nodes per round without
    pre-unrolling max iterations.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     ConversationalToolLoopTemplate, GraphTemplateParams,
        ... )
        >>> graph = ConversationalToolLoopTemplate().instantiate(
        ...     GraphTemplateParams(goal="chat tools", inputs={"max_iterations": 4})
        ... )
        >>> graph.template_name
        'conversational_tool_loop'
        >>> "tools" in graph.nodes
        True
    """

    name = "conversational_tool_loop"
    version = "1"
    summary = (
        "Bounded conversational tool loop: expand inference and per-tool-call "
        "nested graph nodes under a tools parent without pre-unrolling rounds."
    )
    soft_points = (
        SoftPoint(
            name="tools_kind",
            kind="runner_kind",
            description="Runner kind for the tools controller node",
            default="conversational_tool_loop",
        ),
        SoftPoint(
            name="inference_kind",
            kind="runner_kind",
            description="Node kind for each model complete step",
            default="inference",
        ),
        SoftPoint(
            name="tool_call_kind",
            kind="runner_kind",
            description="Node kind for each tool invocation",
            default="tool_call",
        ),
        SoftPoint(
            name="stop_contract",
            kind="budget",
            description="Bound on tool-loop rounds",
            required=False,
        ),
        SoftPoint(
            name="max_iterations",
            kind="budget",
            description="Max rounds when stop_contract omitted",
            default=8,
        ),
        SoftPoint(
            name="message_state_key",
            kind="task_state",
            description="Carried message / state key for the loop",
            required=False,
            default="messages",
        ),
        SoftPoint(
            name="tool_dispatch",
            kind="tool",
            description="Host tool dispatch binding",
            required=False,
        ),
        SoftPoint(
            name="inference",
            kind="provider",
            description="Host inference / complete binding",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = params.inputs
        max_iterations = int(
            bindings.get("max_iterations", inputs.get("max_iterations", 8))
        )
        stop = params.stop_contract or StopContract(
            version="1", max_iterations=max_iterations
        )
        tools_kind = str(bindings.get("tools_kind", "conversational_tool_loop"))
        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        tools = make_node(
            id="tools",
            kind=tools_kind,
            goal="bounded conversational tool loop",
            repeating=True,
            stop_contract=stop,
            payload={
                "phase": "tools",
                "inference_kind": str(bindings.get("inference_kind", "inference")),
                "tool_call_kind": str(bindings.get("tool_call_kind", "tool_call")),
                "message_state_key": str(
                    bindings.get(
                        "message_state_key",
                        inputs.get("message_state_key", "messages"),
                    )
                ),
                "max_iterations": max_iterations,
            },
        )
        graph.add_node(tools)
        return graph
