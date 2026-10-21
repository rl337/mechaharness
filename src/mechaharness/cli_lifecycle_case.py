"""Product CLI verb: lifecycle-extension case plans (observe / rewrite / block / replace).

One verb (``lifecycle_case``) loads a YAML plan whose ``case:`` field selects
the demo extension mode. Hosts swap in real ``LifecycleExtension`` subclasses
via Config; these cases exercise the product registry seam with host-shaped
demo mods.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Union, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

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

CaseKind = Literal[
    "observe",
    "rewrite",
    "block",
    "replace",
    "graph_observe",
]

_LEGACY_PROBE_NAMES: dict[str, CaseKind] = {
    "lifecycle_extension_observe": "observe",
    "lifecycle_extension_rewrite": "rewrite",
    "lifecycle_extension_block": "block",
    "lifecycle_extension_replace": "replace",
    "lifecycle_extension_graph_observe": "graph_observe",
}


class _ScriptedCompleter(InferenceStrategy):
    """Minimal scripted completer for lifecycle demo cases (no network)."""

    name = "lifecycle_scripted"

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


async def _run_tool_lifecycle(
    *,
    prompt: str,
    tool_calls: list[dict[str, Any]],
    grants: list[Any] | None,
    extensions: list[LifecycleExtension],
) -> dict[str, Any]:
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


class ObserveCase(BaseModel):
    """Ordered observe-before extensions without changing the tool call."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["observe"] = "observe"
    summary: str = ""
    prompt: str = "write"
    grants: list[Any] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)

    async def run(self) -> dict[str, Any]:
        actual = await _run_tool_lifecycle(
            prompt=self.prompt,
            tool_calls=list(self.tool_calls),
            grants=list(self.grants) or None,
            extensions=[_WatchA(), _WatchB()],
        )
        return {
            "summary": self.summary,
            "extension_ids": actual["extension_ids"],
            "orders": actual["orders"],
            "default_ran": actual["default_ran"],
            "tool_result": actual["tool_result"],
        }


class RewriteCase(BaseModel):
    """Rewrite tool arguments at BeforeTool; default still runs."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["rewrite"] = "rewrite"
    summary: str = ""
    prompt: str = "write"
    grants: list[Any] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)

    async def run(self) -> dict[str, Any]:
        actual = await _run_tool_lifecycle(
            prompt=self.prompt,
            tool_calls=list(self.tool_calls),
            grants=list(self.grants) or None,
            extensions=[_SandboxRewrite()],
        )
        return {
            "summary": self.summary,
            "tool_result": actual["tool_result"],
            "applied_rewrite": actual["applied_rewrite"],
            "default_ran": actual["default_ran"],
        }


class BlockCase(BaseModel):
    """Block a tool call and emit a host block message."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["block"] = "block"
    summary: str = ""
    prompt: str = "write"
    grants: list[Any] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)

    async def run(self) -> dict[str, Any]:
        actual = await _run_tool_lifecycle(
            prompt=self.prompt,
            tool_calls=list(self.tool_calls),
            grants=list(self.grants) or None,
            extensions=[_BlockWrite()],
        )
        return {
            "summary": self.summary,
            "tool_result": actual["tool_result"],
            "applied_block": actual["applied_block"],
            "default_ran": actual["default_ran"],
        }


class ReplaceCase(BaseModel):
    """Replace tool execution with host-provided content."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["replace"] = "replace"
    summary: str = ""
    prompt: str = "write"
    grants: list[Any] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)

    async def run(self) -> dict[str, Any]:
        actual = await _run_tool_lifecycle(
            prompt=self.prompt,
            tool_calls=list(self.tool_calls),
            grants=list(self.grants) or None,
            extensions=[_ReplaceWrite()],
        )
        return {
            "summary": self.summary,
            "tool_result": actual["tool_result"],
            "applied_replace": actual["applied_replace"],
            "default_ran": actual["default_ran"],
        }


class GraphObserveCase(BaseModel):
    """Observe graph node attempts without replacing failure policy."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["graph_observe"] = "graph_observe"
    summary: str = ""
    goal: str = "lifecycle"

    async def run(self) -> dict[str, Any]:
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
                return LifecycleExtensionRegistry([_GraphWatch()])

        executor = cast(GraphExecutor, get_injector(Cfg()).inject(GraphExecutor))
        graph = ExecutionGraph(goal=self.goal)
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
            "summary": self.summary,
            "graph_status": result.status,
            "boundary": before.payload.get("boundary") if before else None,
            "extension_id": before.payload.get("extension_id") if before else None,
            "default_ran": (
                bool(before.payload.get("default_ran")) if before else False
            ),
            "budget_spent": spent,
            "cost_units": spent,
        }


LifecycleCaseDocument = Union[
    ObserveCase,
    RewriteCase,
    BlockCase,
    ReplaceCase,
    GraphObserveCase,
]

_CASE_MODELS: dict[str, type[BaseModel]] = {
    "observe": ObserveCase,
    "rewrite": RewriteCase,
    "block": BlockCase,
    "replace": ReplaceCase,
    "graph_observe": GraphObserveCase,
}


def load_lifecycle_case(raw: dict[str, Any]) -> LifecycleCaseDocument:
    case = raw.get("case")
    if case is None and "name" in raw:
        name = str(raw["name"])
        case = _LEGACY_PROBE_NAMES.get(name, name)
        raw = {**raw, "case": case}
        raw.pop("name", None)
    if case not in _CASE_MODELS:
        known = ", ".join(sorted(_CASE_MODELS))
        raise ValueError(f"unknown lifecycle case {case!r}; known: {known}")
    return cast(LifecycleCaseDocument, _CASE_MODELS[case].model_validate(raw))


def load_lifecycle_case_path(path: str | Path) -> LifecycleCaseDocument:
    file_path = Path(path)
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: lifecycle case root must be a mapping")
    return load_lifecycle_case(data)


async def run_lifecycle_case_document(
    document: LifecycleCaseDocument,
) -> dict[str, Any]:
    return await document.run()


class LifecycleCaseCommand(BaseModel):
    """CLI verb body: ``path`` to a case plan, or inline ``case:`` document."""

    model_config = ConfigDict(extra="allow")

    path: str | None = None
    case: CaseKind | None = None

    @model_validator(mode="after")
    def _path_or_inline(self) -> LifecycleCaseCommand:
        if self.path:
            return self
        if not self.case:
            raise ValueError("lifecycle_case requires path= or case=")
        return self

    async def resolve_and_run(self, *, base_dir: Path | None = None) -> dict[str, Any]:
        if self.path:
            file_path = Path(self.path)
            if not file_path.is_absolute():
                root = base_dir if base_dir is not None else Path.cwd()
                file_path = (root / file_path).resolve()
            document = load_lifecycle_case_path(file_path)
        else:
            document = load_lifecycle_case(self.model_dump(exclude={"path"}))
        return await run_lifecycle_case_document(document)


class LifecycleCaseVerb(CliVerb):
    """Product verb: run a lifecycle-extension case plan."""

    name = "lifecycle_case"
    params_model = LifecycleCaseCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = params
        assert isinstance(body, LifecycleCaseCommand)
        return await body.resolve_and_run(base_dir=runtime.bind_base_dir)


__all__ = [
    "BlockCase",
    "CaseKind",
    "GraphObserveCase",
    "LifecycleCaseCommand",
    "LifecycleCaseDocument",
    "LifecycleCaseVerb",
    "ObserveCase",
    "ReplaceCase",
    "RewriteCase",
    "load_lifecycle_case",
    "load_lifecycle_case_path",
    "run_lifecycle_case_document",
]
