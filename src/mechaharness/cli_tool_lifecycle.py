"""Product CLI verb: run a tool-loop (or tiny graph) with Config-bound lifecycle extensions."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.cli_verb import CliVerb
from mechaharness.core.access import Ability, AccessPolicy, FsWrite, GraphExecute
from mechaharness.core.completer import Completer
from mechaharness.core.events import InMemoryEventLog
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    ToolCall,
    Usage,
)
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphExecutor,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.lifecycle_extension import (
    LifecycleExtension,
    LifecycleExtensionRegistry,
)
from mechaharness.tools.base import ToolRegistry


class _ScriptedCompleter(InferenceStrategy):
    name = "tool_lifecycle_scripted"

    def __init__(self, responses: list[ChatMessage]) -> None:
        self._responses = list(responses)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        del request
        usage = Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        if not self._responses:
            return CompletionResponse(
                message=ChatMessage(
                    role=Role.ASSISTANT, content="(no scripted response left)"
                ),
                finish_reason="stop",
                usage=usage,
            )
        message = self._responses.pop(0)
        finish = "tool_calls" if message.tool_calls else "stop"
        return CompletionResponse(message=message, finish_reason=finish, usage=usage)


def _write_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(
        description="Write a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        grants=[FsWrite],
        ability=Ability.BASIC,
    )
    def write_file(path: str) -> str:
        return f"wrote {path}"

    return registry


def _parse_grants(raw: list[Any] | None) -> list[object]:
    if not raw:
        return [FsWrite]
    out: list[object] = []
    for item in raw:
        if item in ("core:fs.write", "FsWrite", FsWrite):
            out.append(FsWrite)
        else:
            out.append(item)
    return out


async def run_tool_lifecycle(
    *,
    prompt: str,
    tool_calls: list[dict[str, Any]],
    grants: list[Any] | None,
    extensions: list[LifecycleExtension],
) -> dict[str, Any]:
    """Execute one tool-loop turn with host lifecycle extensions applied."""
    calls = [
        ToolCall(
            id=str(tc["id"]),
            name=str(tc["name"]),
            arguments=dict(tc.get("arguments") or {}),
        )
        for tc in tool_calls
    ]
    inference = _ScriptedCompleter(
        [
            ChatMessage(role=Role.ASSISTANT, content=None, tool_calls=calls),
            ChatMessage(role=Role.ASSISTANT, content="done"),
        ]
    )
    log = InMemoryEventLog()
    grant_list = _parse_grants(grants)
    registry = LifecycleExtensionRegistry(extensions)

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return type(inference)

        def get_harness_class(self) -> type[AbstractHarness]:
            return ToolLoopHarness

        def get_tools(self) -> ToolRegistry:
            return _write_tool_registry()

        def get_harness_config(self) -> HarnessConfig:
            return HarnessConfig(model="story", max_turns=4)

        def get_event_log(self) -> InMemoryEventLog:
            return log

        def get_access_policy(self) -> AccessPolicy:
            return AccessPolicy(grants=grant_list)

        def get_lifecycle_extension_registry(self) -> LifecycleExtensionRegistry:
            return registry

        def get_capability_envelope(self) -> CapabilityEnvelope:
            return CapabilityEnvelope.from_grants(grant_list)

        def configure(self) -> None:
            super().configure()
            self.register_instance(InferenceStrategy, inference)
            self.register_instance(Completer, inference)

    harness = get_injector(Cfg()).inject(AbstractHarness)
    result = await harness.run(prompt)
    rid = result.events[0].run_id if result.events else None
    ext_events = [
        e for e in log.query(run_id=rid) if e.type == "core:extension_applied"
    ]
    tool_msgs = [m.content or "" for m in result.messages if m.role == Role.TOOL]
    tool_result = tool_msgs[0] if tool_msgs else ""
    before_events = [
        e for e in ext_events if e.payload.get("boundary") == "core:before_tool"
    ]
    focus = before_events or ext_events
    return {
        "extension_ids": [e.payload.get("extension_id") for e in focus],
        "orders": [e.payload.get("order") for e in focus],
        "default_ran": all(bool(e.payload.get("default_ran")) for e in focus)
        if focus
        else False,
        "applied_rewrite": any(bool(e.payload.get("applied_rewrite")) for e in focus),
        "applied_block": any(bool(e.payload.get("applied_block")) for e in focus),
        "applied_replace": any(bool(e.payload.get("applied_replace")) for e in focus),
        "tool_result": tool_result,
    }


async def run_graph_lifecycle(
    *,
    goal: str,
    extensions: list[LifecycleExtension],
) -> dict[str, Any]:
    """Observe BeforeGraphNode extensions on a tiny compute graph."""
    log = InMemoryEventLog()

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

        def get_event_log(self) -> InMemoryEventLog:
            return log

        def get_lifecycle_extension_registry(self) -> LifecycleExtensionRegistry:
            return LifecycleExtensionRegistry(extensions)

    executor = cast(GraphExecutor, get_injector(Cfg()).inject(GraphExecutor))
    graph = ExecutionGraph(goal=goal)
    graph.add_node(GraphNode(id="a", kind="compute"))
    result = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="lifecycle-graph"
    )
    ext_events = [
        e
        for e in log.query(run_id="lifecycle-graph")
        if e.type == "core:extension_applied"
    ]
    before = next(
        (
            e
            for e in ext_events
            if e.payload.get("boundary") == "core:before_graph_node"
        ),
        None,
    )
    spent = float(result.budget_spent)
    return {
        "graph_status": result.status,
        "boundary": before.payload.get("boundary") if before else None,
        "extension_id": before.payload.get("extension_id") if before else None,
        "default_ran": bool(before.payload.get("default_ran")) if before else False,
        "budget_spent": spent,
        "cost_units": spent,
    }


class ToolLifecycleCommand(BaseModel):
    """Walk tool or graph lifecycle with host-bound extensions (no case bag)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["tool", "graph"] = "tool"
    summary: str = ""
    prompt: str = "write"
    grants: list[Any] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    extension_ids: list[str] = Field(default_factory=list)
    goal: str = "lifecycle"


class ToolLifecycleVerb(CliVerb):
    name = "tool_lifecycle"
    params_model = ToolLifecycleCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = params
        assert isinstance(body, ToolLifecycleCommand)
        catalog: dict[str, LifecycleExtension] = getattr(
            runtime, "lifecycle_extensions", {}
        ) or {}
        extensions: list[LifecycleExtension] = []
        for eid in body.extension_ids:
            ext = catalog.get(eid)
            if ext is None:
                raise KeyError(
                    f"unknown lifecycle extension {eid!r}; "
                    f"known: {sorted(catalog)}"
                )
            extensions.append(ext)
        if body.mode == "graph":
            out = await run_graph_lifecycle(goal=body.goal, extensions=extensions)
        else:
            out = await run_tool_lifecycle(
                prompt=body.prompt,
                tool_calls=list(body.tool_calls),
                grants=list(body.grants) or None,
                extensions=extensions,
            )
        out["summary"] = body.summary
        return out


__all__ = [
    "ToolLifecycleCommand",
    "ToolLifecycleVerb",
    "run_graph_lifecycle",
    "run_tool_lifecycle",
]
