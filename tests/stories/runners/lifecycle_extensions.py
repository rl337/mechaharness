"""Lifecycle extension story runners."""

from __future__ import annotations

from typing import Any

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import (
    Ability,
    AccessPolicy,
    FsWrite,
    GraphExecute,
)
from mechaharness.core.events import InMemoryEventLog
from mechaharness.core.types import ChatMessage, Role, ToolCall
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
    NodeStatus,
)
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
from mechaharness.lifecycle_extension import (
    BeforeGraphNode,
    BeforeTool,
    Block,
    ExtensionEffect,
    LifecycleExtension,
    LifecycleExtensionContext,
    LifecycleExtensionRegistry,
    ObserveBefore,
    Replace,
    Rewrite,
)
from mechaharness.tools.base import ToolRegistry
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import StoryRunner, _assert_expect
from tests.support.di import make_harness


class _WatchA(LifecycleExtension):
    extension_id = "acme:watch_a"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key(), notes={"tag": "a"})


class _WatchB(LifecycleExtension):
    extension_id = "acme:watch_b"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key(), notes={"tag": "b"})


class _SandboxRewrite(LifecycleExtension):
    extension_id = "acme:sandbox_rewrite"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({Rewrite})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        path = str(context.arguments.get("path", ""))
        return ExtensionEffect(
            mode=Rewrite.key(),
            rewrite_arguments={"path": f"/sandbox/{path}"},
        )


class _BlockWrite(LifecycleExtension):
    extension_id = "acme:block_write"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({Block})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(
            mode=Block.key(),
            block=True,
            block_message="blocked by host extension",
        )


class _ReplaceWrite(LifecycleExtension):
    extension_id = "acme:replace_write"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({Replace})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(
            mode=Replace.key(),
            replace_content="hand-off: skipped write",
        )


class _GraphWatch(LifecycleExtension):
    extension_id = "acme:graph_watch"
    version = "1"
    boundary = BeforeGraphNode
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key())


def _lifecycle_write_registry() -> ToolRegistry:
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


async def _run_lifecycle_tool_story(
    case: StoryCase,
    *,
    extensions: list[LifecycleExtension],
) -> dict[str, Any]:
    request = case.load_json("request.json")
    response = case.load_json("response.json")
    tool_calls = [
        ToolCall(
            id=tc["id"],
            name=tc["name"],
            arguments=tc.get("arguments") or {},
        )
        for tc in response.get("tool_calls", [])
    ]
    inference = ScriptedInference(
        [
            ChatMessage(role=Role.ASSISTANT, content=None, tool_calls=tool_calls),
            ChatMessage(role=Role.ASSISTANT, content="done"),
        ]
    )
    log = InMemoryEventLog()
    grants = list(request.get("grants", [FsWrite]))
    result = await make_harness(
        inference,
        tools=_lifecycle_write_registry(),
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=log,
        access_policy=AccessPolicy(grants=grants),
        lifecycle_extensions=LifecycleExtensionRegistry(extensions),
        capability_envelope=CapabilityEnvelope.from_grants(grants),
    ).run(request.get("prompt", "write"))
    rid = result.events[0].run_id if result.events else None
    ext_events = [
        e for e in log.query(run_id=rid) if e.type == "core:extension_applied"
    ]
    tool_msgs = [m.content or "" for m in result.messages if m.role == Role.TOOL]
    tool_result = tool_msgs[0] if tool_msgs else ""
    # Mutative flags / default_ran are taken from before_tool events only.
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
        "tool_result_contains": tool_result,
    }


async def _run_lifecycle_extension_observe(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    actual = await _run_lifecycle_tool_story(case, extensions=[_WatchA(), _WatchB()])
    # Also ensure AfterTool observers are optional; before-tool order is the claim.
    _assert_expect(
        {
            "extension_ids": actual["extension_ids"],
            "orders": actual["orders"],
            "default_ran": actual["default_ran"],
            "tool_result_contains": actual["tool_result_contains"],
        },
        expect,
    )


async def _run_lifecycle_extension_rewrite(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    actual = await _run_lifecycle_tool_story(case, extensions=[_SandboxRewrite()])
    _assert_expect(
        {
            "tool_result_contains": actual["tool_result_contains"],
            "applied_rewrite": actual["applied_rewrite"],
            "default_ran": actual["default_ran"],
        },
        expect,
    )


async def _run_lifecycle_extension_block(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    actual = await _run_lifecycle_tool_story(case, extensions=[_BlockWrite()])
    _assert_expect(
        {
            "tool_result_contains": actual["tool_result_contains"],
            "applied_block": actual["applied_block"],
            "default_ran": actual["default_ran"],
        },
        expect,
    )


async def _run_lifecycle_extension_replace(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    actual = await _run_lifecycle_tool_story(case, extensions=[_ReplaceWrite()])
    _assert_expect(
        {
            "tool_result_contains": actual["tool_result_contains"],
            "applied_replace": actual["applied_replace"],
            "default_ran": actual["default_ran"],
        },
        expect,
    )


async def _run_lifecycle_extension_graph_observe(
    case: StoryCase, backend: StoryBackend
) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    log = InMemoryEventLog()

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

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
            return LifecycleExtensionRegistry([_GraphWatch()])

    executor = get_injector(Cfg()).inject(GraphExecutor)
    graph = ExecutionGraph(goal=str(request.get("goal") or "lifecycle"))
    graph.add_node(GraphNode(id="a", kind="compute"))
    result = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="lifecycle-graph"
    )
    ext_events = [
        e for e in log.query(run_id="lifecycle-graph") if e.type == "core:extension_applied"
    ]
    before = next(
        (e for e in ext_events if e.payload.get("boundary") == "core:before_graph_node"),
        None,
    )
    actual = {
        "graph_status": result.status,
        "boundary": before.payload.get("boundary") if before else None,
        "extension_id": before.payload.get("extension_id") if before else None,
        "default_ran": bool(before.payload.get("default_ran")) if before else False,
    }
    _assert_expect(actual, expect)



RUNNERS: dict[str, StoryRunner] = {
    "lifecycle_extension_observe": _run_lifecycle_extension_observe,
    "lifecycle_extension_rewrite": _run_lifecycle_extension_rewrite,
    "lifecycle_extension_block": _run_lifecycle_extension_block,
    "lifecycle_extension_replace": _run_lifecycle_extension_replace,
    "lifecycle_extension_graph_observe": _run_lifecycle_extension_graph_observe,
}
