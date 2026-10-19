"""Host CLI instrumentor over the concrete ``cli_universe`` graph.

Verb-led commands (``infer``, ``tool_loop``, ``run_recipe``, diagnostics,
``set_clock``, ``advance_clock``) with optional parameterization and good
defaults. Story YAML may attach test-only ``expect`` blocks; this module
returns observations and does not assert.

See ``docs/reference/cli-universe.md``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pyiv.time import DateTimeService, MockDateTimeService

from mechaharness.budget import BudgetPolicy
from mechaharness.cli_diagnostic_verbs import (
    CheckModelAffinityCommand,
    CompareRunParityCommand,
    ReplayModelInputCommand,
    RouteCapabilitiesCommand,
    ShadowDecisionBackendsCommand,
    run_check_model_affinity,
    run_compare_run_parity,
    run_replay_model_input,
    run_route_capabilities,
    run_shadow_decision_backends,
)
from mechaharness.cli_infer_runner import CliInferRunner
from mechaharness.cli_universe import CLI_INFER_NODE_ID, build_cli_universe_graph
from mechaharness.config import Settings
from mechaharness.conversational_tool_loop_runner import ConversationalToolLoopRunner
from mechaharness.core.access import CostAccountant, InMemoryCostAccountant
from mechaharness.core.completer import Completer
from mechaharness.core.contract import RunRequest
from mechaharness.core.events import (
    AgentRef,
    Event,
    EventLog,
    EventTypeRef,
    InMemoryEventLog,
)
from mechaharness.core.types import ChatMessage, CompletionRequest, Role
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.graph import ExecutionGraph
from mechaharness.graph_executor import GraphNodeRunnerRegistry
from mechaharness.graph_templates import ConversationalToolLoopTemplate, GraphTemplateParams
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.host_kit import host_graph_executor, tapping_event_log
from mechaharness.inference.base import InferenceStrategy
from mechaharness.node_component import traversal_from_events
from mechaharness.recipe_runner import (
    instantiate_recipe,
    list_recipes,
    run_backend_describe_recipe,
    run_harness_recipe,
)
from mechaharness.tools.base import Tool, ToolRegistry


class StampingEventLog(EventLog):
    """EventLog adapter that stamps ``Event.ts`` from a :class:`DateTimeService`."""

    def __init__(self, inner: EventLog, datetime_service: DateTimeService) -> None:
        self._inner = inner
        self._datetime = datetime_service

    def emit(self, event: Event) -> None:
        self._inner.emit(
            event.model_copy(update={"ts": self._datetime.now_utc()})
        )

    def query(
        self,
        *,
        agent_id: str | None = None,
        run_id: str | None = None,
        descendants: bool = False,
        types: Sequence[EventTypeRef] | None = None,
    ) -> list[Event]:
        return self._inner.query(
            agent_id=agent_id,
            run_id=run_id,
            descendants=descendants,
            types=types,
        )

    def agents(self, *, parent_id: str | None = None) -> list[AgentRef]:
        return self._inner.agents(parent_id=parent_id)

    @property
    def inner(self) -> EventLog:
        return self._inner


class InferCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    system: str = ""
    model: str | None = None


class ToolLoopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    tool_name: str = "lookup"
    max_turns: int = 4
    model: str | None = None


class RunRecipeCommand(BaseModel):
    """Execute a catalog recipe through the CLI instrumentor (Wave 2+)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    prompt: str | None = None
    backend: str = "mock"
    family: str = "pass_through"
    max_turns: int = 4
    max_iterations: int = 4
    tool_name: str = "lookup"
    model: str | None = None


class SetClockCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str  # ISO-8601 UTC


class AdvanceClockCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seconds: float = 0
    minutes: float = 0
    hours: float = 0


class CliCommand(BaseModel):
    """Exactly one verb key per command."""

    model_config = ConfigDict(extra="forbid")

    infer: InferCommand | None = None
    tool_loop: ToolLoopCommand | None = None
    run_recipe: RunRecipeCommand | None = None
    replay_model_input: ReplayModelInputCommand | None = None
    route_capabilities: RouteCapabilitiesCommand | None = None
    check_model_affinity: CheckModelAffinityCommand | None = None
    compare_run_parity: CompareRunParityCommand | None = None
    shadow_decision_backends: ShadowDecisionBackendsCommand | None = None
    set_clock: SetClockCommand | None = None
    advance_clock: AdvanceClockCommand | None = None

    @model_validator(mode="after")
    def _one_verb(self) -> CliCommand:
        verbs = [
            ("infer", self.infer),
            ("tool_loop", self.tool_loop),
            ("run_recipe", self.run_recipe),
            ("replay_model_input", self.replay_model_input),
            ("route_capabilities", self.route_capabilities),
            ("check_model_affinity", self.check_model_affinity),
            ("compare_run_parity", self.compare_run_parity),
            ("shadow_decision_backends", self.shadow_decision_backends),
            ("set_clock", self.set_clock),
            ("advance_clock", self.advance_clock),
        ]
        present = [n for n, b in verbs if b is not None]
        if len(present) != 1:
            raise ValueError(
                f"each command needs exactly one verb; got {present or 'none'}"
            )
        return self

    @property
    def verb(self) -> str:
        for name in (
            "infer",
            "tool_loop",
            "run_recipe",
            "replay_model_input",
            "route_capabilities",
            "check_model_affinity",
            "compare_run_parity",
            "shadow_decision_backends",
            "set_clock",
            "advance_clock",
        ):
            if getattr(self, name) is not None:
                return name
        raise RuntimeError("CliCommand missing verb")


class CliScript(BaseModel):
    """Product CLI script (no test expects)."""

    model_config = ConfigDict(extra="forbid")

    commands: list[CliCommand] = Field(min_length=1)


class CliStepResult(BaseModel):
    """Outcome of one CLI command for hosts and hard story checks."""

    model_config = ConfigDict(extra="forbid")

    verb: str
    text: str | None = None
    status: str | None = None
    event_types: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    cost_units: float = 0.0
    clock_iso: str | None = None
    traversal_kinds: list[str] = Field(default_factory=list)
    component_parent_ids: list[str] = Field(default_factory=list)
    rounds: int | None = None
    turns: int | None = None
    recipe_in_catalog: bool | None = None
    description_name: str | None = None
    subgraph_node_ids: list[str] = Field(default_factory=list)
    probe: dict[str, Any] = Field(default_factory=dict)

    def as_expect_dict(self) -> dict[str, Any]:
        data = {
            "verb": self.verb,
            "text": self.text,
            "status": self.status,
            "event_types": list(self.event_types),
            "event_types_exactly": list(self.event_types),
            "cost_units": self.cost_units,
            "units_positive": self.cost_units > 0,
            "clock_iso": self.clock_iso,
            "inference_ts": _first_ts(self.events, "core:inference"),
            "cost_ts": _first_ts(self.events, "core:cost"),
            "traversal_kinds": list(self.traversal_kinds),
            "traversal_kinds_exactly": list(self.traversal_kinds),
            "component_parent_ids": list(self.component_parent_ids),
            "component_parents_exactly": list(self.component_parent_ids),
            "rounds": self.rounds,
            "turns": self.turns,
            "recipe_in_catalog": self.recipe_in_catalog,
            "description_name": self.description_name,
            "subgraph_node_ids": list(self.subgraph_node_ids),
            "subgraph_node_ids_exactly": list(self.subgraph_node_ids),
            "graph_node_ids_exactly": list(self.subgraph_node_ids),
            "text_nonempty": bool(self.text and str(self.text).strip()),
        }
        data.update(self.probe)
        return data


class CliRunResult(BaseModel):
    """Full script run: per-command steps plus aggregate event view."""

    model_config = ConfigDict(extra="forbid")

    steps: list[CliStepResult] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)
    tapped_event_types: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    cost_units: float = 0.0
    text: str | None = None
    status: str | None = None
    traversal_kinds: list[str] = Field(default_factory=list)
    component_parent_ids: list[str] = Field(default_factory=list)
    rounds: int | None = None
    turns: int | None = None
    recipe_in_catalog: bool | None = None
    description_name: str | None = None
    subgraph_node_ids: list[str] = Field(default_factory=list)
    probe: dict[str, Any] = Field(default_factory=dict)

    def as_expect_dict(self) -> dict[str, Any]:
        data = {
            "event_types": list(self.event_types),
            "event_types_exactly": list(self.event_types),
            "tapped_event_types": list(self.tapped_event_types),
            "tapped_event_types_exactly": list(self.tapped_event_types),
            "cost_units": self.cost_units,
            "units_positive": self.cost_units > 0,
            "text": self.text,
            "text_nonempty": bool(self.text and str(self.text).strip()),
            "status": self.status,
            "inference_ts": _first_ts(self.events, "core:inference"),
            "cost_ts": _first_ts(self.events, "core:cost"),
            "traversal_kinds": list(self.traversal_kinds),
            "traversal_kinds_exactly": list(self.traversal_kinds),
            "component_parent_ids": list(self.component_parent_ids),
            "component_parents_exactly": list(self.component_parent_ids),
            "rounds": self.rounds,
            "turns": self.turns,
            "recipe_in_catalog": self.recipe_in_catalog,
            "description_name": self.description_name,
            "subgraph_node_ids": list(self.subgraph_node_ids),
            "subgraph_node_ids_exactly": list(self.subgraph_node_ids),
            "graph_node_ids_exactly": list(self.subgraph_node_ids),
        }
        data.update(self.probe)
        return data


class _CliToolLoopConfig(MechaHarnessConfig):
    """Bind a host-supplied Completer + tools for the ``tool_loop`` verb."""

    def __init__(
        self,
        completer: Completer,
        *,
        tools: ToolRegistry,
        harness_config: HarnessConfig,
        event_log: EventLog,
        agent_id: str,
    ) -> None:
        self._completer = completer
        self._tools = tools
        self._harness_config = harness_config
        self._provided_event_log = event_log
        self._agent_id = agent_id
        super().__init__()

    def get_inference_class(self) -> type[InferenceStrategy]:
        if isinstance(self._completer, InferenceStrategy):
            return type(self._completer)
        from mechaharness.inference.mock import MockInferenceStrategy

        return MockInferenceStrategy

    def get_harness_class(self) -> type[AbstractHarness]:
        return ToolLoopHarness

    def get_tools(self) -> ToolRegistry:
        return self._tools

    def get_harness_config(self) -> HarnessConfig:
        return self._harness_config

    def get_event_log(self) -> EventLog | None:
        return self._provided_event_log

    def configure(self) -> None:
        super().configure()
        if isinstance(self._completer, InferenceStrategy):
            self.register_instance(InferenceStrategy, self._completer)
        self.register_instance(Completer, self._completer)


class CliInstrumentor:
    """Run a :class:`CliScript` against the concrete CLI universe graph."""

    def __init__(
        self,
        completer: Completer,
        *,
        event_log: EventLog | None = None,
        datetime_service: DateTimeService | None = None,
        model: str = "cli-default",
        agent_id: str = "cli",
        tools: ToolRegistry | None = None,
    ) -> None:
        self._completer = completer
        self._model = model
        self._agent_id = agent_id
        self._tools = tools if tools is not None else ToolRegistry()
        self._tapped_types: list[str] = []
        self._datetime: DateTimeService = datetime_service or MockDateTimeService(
            datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        )
        store = event_log or InMemoryEventLog()
        stamped = StampingEventLog(store, self._datetime)
        self._log: EventLog = tapping_event_log(
            stamped,
            on_event=lambda e: self._tapped_types.append(str(getattr(e, "type", ""))),
        )
        self._cost: CostAccountant = InMemoryCostAccountant(self._log)
        self._runner = CliInferRunner(
            self._completer,
            self._cost,
            self._log,
            model=self._model,
        )
        self._executor = host_graph_executor(
            runners=GraphNodeRunnerRegistry([self._runner]),
            event_log=self._log,
            agent_id=self._agent_id,
        )

    @property
    def event_log(self) -> EventLog:
        return self._log

    @property
    def datetime_service(self) -> DateTimeService:
        return self._datetime

    @property
    def tapped_event_types(self) -> list[str]:
        return list(self._tapped_types)

    async def run(self, script: CliScript) -> CliRunResult:
        steps: list[CliStepResult] = []
        last_text: str | None = None
        last_status: str | None = None
        last_traversal: list[str] = []
        last_parents: list[str] = []
        last_rounds: int | None = None
        last_turns: int | None = None
        last_in_catalog: bool | None = None
        last_description: str | None = None
        last_subgraph_ids: list[str] = []
        last_probe: dict[str, Any] = {}
        for command in script.commands:
            step = await self._run_command(command)
            steps.append(step)
            if step.text is not None:
                last_text = step.text
            if step.status is not None:
                last_status = step.status
            if step.traversal_kinds:
                last_traversal = list(step.traversal_kinds)
            if step.component_parent_ids:
                last_parents = list(step.component_parent_ids)
            if step.rounds is not None:
                last_rounds = step.rounds
            if step.turns is not None:
                last_turns = step.turns
            if step.recipe_in_catalog is not None:
                last_in_catalog = step.recipe_in_catalog
            if step.description_name is not None:
                last_description = step.description_name
            if step.subgraph_node_ids:
                last_subgraph_ids = list(step.subgraph_node_ids)
            if step.probe:
                last_probe = dict(step.probe)
        all_events = self._log.query(agent_id=self._agent_id)
        # Tool-loop harness may emit under a different filter; fall back to all.
        if not all_events:
            all_events = self._log.query()
        types = [e.type for e in all_events]
        units = sum(
            float(e.payload.get("units") or 0)
            for e in all_events
            if e.type == "core:cost"
        )
        return CliRunResult(
            steps=steps,
            event_types=types,
            tapped_event_types=list(self._tapped_types),
            events=[_event_dict(e) for e in all_events],
            cost_units=units,
            text=last_text,
            status=last_status,
            traversal_kinds=last_traversal,
            component_parent_ids=last_parents,
            rounds=last_rounds,
            turns=last_turns,
            recipe_in_catalog=last_in_catalog,
            description_name=last_description,
            subgraph_node_ids=last_subgraph_ids,
            probe=last_probe,
        )

    async def _run_command(self, command: CliCommand) -> CliStepResult:
        before = len(self._log.query())
        if command.set_clock is not None:
            self._set_clock(command.set_clock.at)
            return CliStepResult(
                verb="set_clock",
                clock_iso=self._datetime.now_utc_iso(),
            )
        if command.advance_clock is not None:
            self._advance_clock(command.advance_clock)
            return CliStepResult(
                verb="advance_clock",
                clock_iso=self._datetime.now_utc_iso(),
            )
        if command.tool_loop is not None:
            return await self._run_tool_loop(command.tool_loop, before=before)
        if command.run_recipe is not None:
            return await self._run_recipe(command.run_recipe, before=before)
        if command.replay_model_input is not None:
            return CliStepResult(
                verb="replay_model_input",
                probe=run_replay_model_input(command.replay_model_input),
            )
        if command.route_capabilities is not None:
            return CliStepResult(
                verb="route_capabilities",
                probe=run_route_capabilities(command.route_capabilities),
            )
        if command.check_model_affinity is not None:
            return CliStepResult(
                verb="check_model_affinity",
                probe=run_check_model_affinity(command.check_model_affinity),
            )
        if command.compare_run_parity is not None:
            return CliStepResult(
                verb="compare_run_parity",
                probe=run_compare_run_parity(command.compare_run_parity),
            )
        if command.shadow_decision_backends is not None:
            return CliStepResult(
                verb="shadow_decision_backends",
                probe=run_shadow_decision_backends(command.shadow_decision_backends),
            )
        assert command.infer is not None
        body = command.infer
        graph = build_cli_universe_graph(prompt=body.prompt, system=body.system)
        if body.model:
            graph.nodes[CLI_INFER_NODE_ID].payload["model"] = body.model
        result = await self._executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
        )
        after_events = self._log.query()[before:]
        node = result.graph.nodes.get(CLI_INFER_NODE_ID)
        text = None
        if node is not None:
            text = str((node.payload or {}).get("text") or "") or None
        units = sum(
            float(e.payload.get("units") or 0)
            for e in after_events
            if e.type == "core:cost"
        )
        return CliStepResult(
            verb="infer",
            text=text,
            status=result.status,
            event_types=[e.type for e in after_events],
            events=[_event_dict(e) for e in after_events],
            cost_units=units,
            clock_iso=self._datetime.now_utc_iso(),
        )

    async def _run_tool_loop(
        self,
        body: ToolLoopCommand,
        *,
        before: int,
    ) -> CliStepResult:
        tools = ToolRegistry()
        for definition in self._tools.definitions():
            tools.register(self._tools.get(definition.name))
        if body.tool_name not in tools:
            tools.register(
                Tool(body.tool_name, lambda: "ok", description="cli tool")
            )
        config = _CliToolLoopConfig(
            self._completer,
            tools=tools,
            harness_config=HarnessConfig(
                model=body.model or self._model,
                max_turns=body.max_turns,
            ),
            event_log=self._log,
            agent_id=self._agent_id,
        )
        harness = get_injector(config).inject(
            AbstractHarness,
            agent_id=self._agent_id,
        )
        result = await harness.run(body.prompt)
        after_events = self._log.query()[before:]
        if not after_events and result.events:
            after_events = list(result.events)
        records = traversal_from_events(
            [{"type": e.type, "payload": e.payload} for e in after_events]
        )
        kinds = [r.kind for r in records]
        parents = [
            str(r.parent_node_id)
            for r in records
            if r.kind in {"inference", "tool_call", "tool_result", "turn_start"}
            and r.parent_node_id is not None
        ]
        units = sum(
            float(e.payload.get("units") or 0)
            for e in after_events
            if e.type == "core:cost"
        )
        return CliStepResult(
            verb="tool_loop",
            text=result.final_text,
            status="ok" if (result.final_text or "").strip() else "failed",
            event_types=[e.type for e in after_events],
            events=[_event_dict(e) for e in after_events],
            cost_units=units,
            clock_iso=self._datetime.now_utc_iso(),
            traversal_kinds=kinds,
            component_parent_ids=parents,
        )

    async def _run_recipe(
        self,
        body: RunRecipeCommand,
        *,
        before: int,
    ) -> CliStepResult:
        if body.name == "conversational_tool_loop":
            return await self._run_conversational_tool_loop(body, before=before)
        if body.name == "harness_run":
            return await self._run_harness_run_recipe(body, before=before)
        if body.name == "backend_describe":
            return await self._run_backend_describe_recipe(body, before=before)
        raise ValueError(
            f"run_recipe does not yet support recipe {body.name!r}"
        )

    async def _run_harness_run_recipe(
        self,
        body: RunRecipeCommand,
        *,
        before: int,
    ) -> CliStepResult:
        if not body.prompt:
            raise ValueError("run_recipe harness_run requires prompt=")
        catalog = {row["name"] for row in list_recipes()}
        response = await run_harness_recipe(
            RunRequest(
                prompt=body.prompt,
                backend=body.backend,
                family=body.family,
                model=body.model or self._model,
                max_turns=body.max_turns,
            ),
            tools=self._tools if len(self._tools) else None,
            event_log=self._log,
        )
        graph = instantiate_recipe(
            "harness_run",
            GraphTemplateParams(
                goal="harness_run",
                inputs={"prompt": body.prompt},
                soft_bindings={
                    "prompt": body.prompt,
                    "backend": body.backend,
                    "family": body.family,
                },
            ),
        )
        after_events = self._log.query()[before:]
        units = sum(
            float(e.payload.get("units") or 0)
            for e in after_events
            if e.type == "core:cost"
        )
        return CliStepResult(
            verb="run_recipe",
            text=response.final_text,
            status="ok",
            event_types=[e.type for e in after_events],
            events=[_event_dict(e) for e in after_events],
            cost_units=units,
            clock_iso=self._datetime.now_utc_iso(),
            turns=int(response.turns or 0),
            recipe_in_catalog="harness_run" in catalog,
            subgraph_node_ids=list(graph.nodes),
        )

    async def _run_backend_describe_recipe(
        self,
        body: RunRecipeCommand,
        *,
        before: int,
    ) -> CliStepResult:
        del before
        catalog = {row["name"] for row in list_recipes()}
        settings = Settings(
            inference_backend=body.backend,
            model=body.model or self._model,
        )
        description = await run_backend_describe_recipe(settings)
        graph = instantiate_recipe(
            "backend_describe",
            GraphTemplateParams(
                goal="backend_describe",
                soft_bindings={"backend": body.backend},
            ),
        )
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status="ok",
            clock_iso=self._datetime.now_utc_iso(),
            recipe_in_catalog="backend_describe" in catalog,
            description_name=str(description.get("name") or ""),
            subgraph_node_ids=list(graph.nodes),
        )

    async def _run_conversational_tool_loop(
        self,
        body: RunRecipeCommand,
        *,
        before: int,
    ) -> CliStepResult:
        tools = ToolRegistry()
        for definition in self._tools.definitions():
            tools.register(self._tools.get(definition.name))
        if body.tool_name not in tools:
            tools.register(
                Tool(body.tool_name, lambda: "ok", description="cli tool")
            )

        async def complete(
            messages: list[dict[str, Any]],
            meta: Mapping[str, Any],
        ) -> dict[str, Any]:
            del messages, meta
            response = await self._completer.complete(
                CompletionRequest(
                    model=self._model,
                    messages=[ChatMessage(role=Role.USER, content="continue")],
                )
            )
            message = response.message
            out: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or "",
            }
            if message.tool_calls:
                out["tool_calls"] = [
                    {
                        "id": call.id,
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in message.tool_calls
                ]
            return out

        def dispatch_tool(name: str, args: Any) -> str:
            del args
            if name in tools:
                return f"ok:{name}"
            return f"ok:{name}"

        runner = ConversationalToolLoopRunner(
            complete=complete,
            dispatch_tool=dispatch_tool,
        )
        graph = ConversationalToolLoopTemplate().instantiate(
            GraphTemplateParams(
                goal="loop",
                inputs={"max_iterations": body.max_iterations},
            )
        )
        executor = host_graph_executor(
            runners=[runner],
            event_log=self._log,
            agent_id=self._agent_id,
        )
        result = await executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            run_id="cli:conversational_tool_loop",
            skip_linkage=True,
        )
        tools_node = result.graph.nodes["tools"]
        child = ExecutionGraph.resume(tools_node.subgraph or {})
        node_ids = list(child.nodes)
        after_events = self._log.query()[before:]
        units = sum(
            float(e.payload.get("units") or 0)
            for e in after_events
            if e.type == "core:cost"
        )
        return CliStepResult(
            verb="run_recipe",
            text=str(tools_node.payload.get("final_text") or "") or None,
            status=result.status,
            event_types=[e.type for e in after_events],
            events=[_event_dict(e) for e in after_events],
            cost_units=units,
            clock_iso=self._datetime.now_utc_iso(),
            rounds=int(tools_node.payload.get("rounds") or 0),
            subgraph_node_ids=node_ids,
        )

    def _set_clock(self, at: str) -> None:
        dts = self._datetime
        if not isinstance(dts, MockDateTimeService):
            raise TypeError(
                "set_clock requires MockDateTimeService "
                f"(got {type(dts).__name__})"
            )
        raw = at.strip().replace("Z", "+00:00")
        when = datetime.fromisoformat(raw)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        dts.set_time(when.astimezone(timezone.utc))

    def _advance_clock(self, body: AdvanceClockCommand) -> None:
        dts = self._datetime
        if not isinstance(dts, MockDateTimeService):
            raise TypeError(
                "advance_clock requires MockDateTimeService "
                f"(got {type(dts).__name__})"
            )
        delta = timedelta(
            seconds=body.seconds,
            minutes=body.minutes,
            hours=body.hours,
        )
        dts.set_time(dts.now_utc() + delta)


def script_from_mapping(data: dict[str, Any]) -> CliScript:
    """Build a product script, stripping test-only keys."""
    commands_raw = data.get("commands") or []
    clean: list[dict[str, Any]] = []
    for raw in commands_raw:
        if not isinstance(raw, dict):
            raise ValueError("each command must be a mapping")
        clean.append(
            {k: v for k, v in raw.items() if k not in {"expect", "expect_error"}}
        )
    return CliScript.model_validate({"commands": clean})


def _event_dict(event: Event) -> dict[str, Any]:
    data = event.model_dump(mode="json")
    ts = data.get("ts")
    if isinstance(ts, str):
        data["ts"] = ts.replace("+00:00", "Z") if ts.endswith("+00:00") else ts
    return data


def _first_ts(events: list[dict[str, Any]], type_key: str) -> str | None:
    for event in events:
        if event.get("type") == type_key:
            ts = event.get("ts")
            return str(ts) if ts is not None else None
    return None


__all__ = [
    "AdvanceClockCommand",
    "CliCommand",
    "CliInstrumentor",
    "CliRunResult",
    "CliScript",
    "CliStepResult",
    "InferCommand",
    "RunRecipeCommand",
    "SetClockCommand",
    "StampingEventLog",
    "ToolLoopCommand",
    "script_from_mapping",
]
