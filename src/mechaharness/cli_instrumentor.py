"""Host CLI instrumentor over the concrete ``cli_universe`` graph.

Verb dispatch is a pyiv map multibind (``cli_verb_classes`` → ``Dict[str, CliVerb]``).
Recipe execution uses ``cli_recipe_adapter_classes``. Story YAML may attach
test-only ``expect`` blocks; this module returns observations and does not assert.

See ``docs/reference/cli-universe.md``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field
from pyiv.time import DateTimeService, MockDateTimeService

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.cli_commands import (
    AdvanceClockCommand,
    InferCommand,
    RunRecipeCommand,
    SetClockCommand,
    ToolLoopCommand,
)
from mechaharness.cli_infer_runner import CliInferRunner
from mechaharness.cli_recipe_adapter import CliRecipeAdapter
from mechaharness.cli_universe import CLI_INFER_NODE_ID, build_cli_universe_graph
from mechaharness.cli_verb import (
    CliParsedCommand,
    CliScript,
    CliVerb,
)
from mechaharness.cli_verb import (
    script_from_mapping as _script_from_mapping,
)
from mechaharness.core.access import (
    AccessControl,
    CostAccountant,
    GrantPolicyLike,
    InMemoryCostAccountant,
)
from mechaharness.core.completer import Completer
from mechaharness.core.events import (
    AgentRef,
    Event,
    EventLog,
    EventTypeRef,
    InMemoryEventLog,
)
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.durable_generator_script import (
    AnswerBody,
    DurableInstrumentor,
    DurableScript,
    InspectBody,
    ListRecipesBody,
    RebuildBody,
    StartBody,
    StepObservation,
)
from mechaharness.graph_executor import GraphNodeRunnerRegistry
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.host_kit import host_graph_executor, tapping_event_log
from mechaharness.host_run_policies import resolve_run_budget
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.judge import JudgeProvider
from mechaharness.node_component import traversal_from_events
from mechaharness.recipe_bind import InstantiateRecipeCommand, TileRecipeCommand
from mechaharness.recipe_plan import RecipePlanCommand
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


class CliStepResult(BaseModel):
    """Outcome of one CLI command for hosts and hard story checks."""

    model_config = ConfigDict(extra="forbid")

    verb: str
    text: str | None = None
    status: str | None = None
    event_types: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    cost_units: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    clock_iso: str | None = None
    traversal_kinds: list[str] = Field(default_factory=list)
    component_parent_ids: list[str] = Field(default_factory=list)
    rounds: int | None = None
    turns: int | None = None
    recipe_in_catalog: bool | None = None
    description_name: str | None = None
    subgraph_node_ids: list[str] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)

    def observation(self) -> dict[str, Any]:
        """Flat observation for structured assertions (no alias minting)."""
        prompt, completion, total = _token_totals(self.events)
        data: dict[str, Any] = {
            "verb": self.verb,
            "text": self.text,
            "status": self.status,
            "event_types": list(self.event_types),
            "cost_units": self.cost_units,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "clock_iso": self.clock_iso,
            "inference_ts": _first_ts(self.events, "core:inference"),
            "cost_ts": _first_ts(self.events, "core:cost"),
            "traversal_kinds": list(self.traversal_kinds),
            "component_parent_ids": list(self.component_parent_ids),
            "rounds": self.rounds,
            "turns": self.turns,
            "recipe_in_catalog": self.recipe_in_catalog,
            "description_name": self.description_name,
            "subgraph_node_ids": list(self.subgraph_node_ids),
        }
        data.update(self.fields)
        return _merge_cost_observation(data)


class CliRunResult(BaseModel):
    """Full script run: per-command steps plus aggregate event view."""

    model_config = ConfigDict(extra="forbid")

    steps: list[CliStepResult] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)
    tapped_event_types: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    cost_units: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    text: str | None = None
    status: str | None = None
    traversal_kinds: list[str] = Field(default_factory=list)
    component_parent_ids: list[str] = Field(default_factory=list)
    rounds: int | None = None
    turns: int | None = None
    recipe_in_catalog: bool | None = None
    description_name: str | None = None
    subgraph_node_ids: list[str] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)

    def observation(self) -> dict[str, Any]:
        prompt, completion, total = _token_totals(self.events)
        data: dict[str, Any] = {
            "event_types": list(self.event_types),
            "tapped_event_types": list(self.tapped_event_types),
            "cost_units": self.cost_units,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "text": self.text,
            "status": self.status,
            "inference_ts": _first_ts(self.events, "core:inference"),
            "cost_ts": _first_ts(self.events, "core:cost"),
            "traversal_kinds": list(self.traversal_kinds),
            "component_parent_ids": list(self.component_parent_ids),
            "rounds": self.rounds,
            "turns": self.turns,
            "recipe_in_catalog": self.recipe_in_catalog,
            "description_name": self.description_name,
            "subgraph_node_ids": list(self.subgraph_node_ids),
        }
        data.update(self.fields)
        return _merge_cost_observation(data)


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
        harness_family: str = "tool_loop",
        grants: list[object] | None = None,
        access_policy: GrantPolicyLike | None = None,
    ) -> None:
        self._completer = completer
        self._tools = tools
        self._harness_config = harness_config
        self._provided_event_log = event_log
        self._agent_id = agent_id
        self._harness_family = harness_family
        self._grants = grants
        self._access_policy = access_policy
        super().__init__()

    def get_inference_class(self) -> type[InferenceStrategy]:
        if isinstance(self._completer, InferenceStrategy):
            return type(self._completer)
        from mechaharness.inference.mock import MockInferenceStrategy

        return MockInferenceStrategy

    def get_harness_class(self) -> type[AbstractHarness]:
        name = self._harness_family.lower()
        classes = self.harness_classes()
        try:
            return classes[name]
        except KeyError as exc:
            known = ", ".join(sorted(classes)) or "(none)"
            raise KeyError(
                f"Unknown harness family {name!r}. Known: {known}"
            ) from exc

    def get_tools(self) -> ToolRegistry:
        return self._tools

    def get_harness_config(self) -> HarnessConfig:
        return self._harness_config

    def get_event_log(self) -> EventLog | None:
        return self._provided_event_log

    def get_grants(self) -> list[object]:
        if self._grants is not None:
            return list(self._grants)
        if self._access_policy is not None:
            return list(self._access_policy.grants)
        return super().get_grants()

    def get_access_policy(self) -> GrantPolicyLike:
        if self._access_policy is not None:
            return self._access_policy
        return super().get_access_policy()

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
        verbs: Mapping[str, CliVerb],
        recipe_adapters: Mapping[str, CliRecipeAdapter],
        datetime_service: DateTimeService,
        *,
        event_log: EventLog | None = None,
        model: str = "cli-default",
        agent_id: str = "cli",
        tools: ToolRegistry | None = None,
        judge_provider: JudgeProvider | None = None,
        rag_retriever: Any | None = None,
        lifecycle_extensions: dict[str, Any] | None = None,
        access_control: AccessControl | None = None,
        capability_envelope: CapabilityEnvelope | None = None,
        budget_policy: BudgetPolicy | None = None,
        grants: Sequence[object] | None = None,
        access_policy: GrantPolicyLike | None = None,
    ) -> None:
        self._completer = completer
        self._model = model
        self._agent_id = agent_id
        self._tools = tools if tools is not None else ToolRegistry()
        self._judge_provider = judge_provider
        self._rag_retriever = rag_retriever
        self._lifecycle_extensions = dict(lifecycle_extensions or {})
        self._verbs = dict(verbs)
        self._recipe_adapters = dict(recipe_adapters)
        self._tapped_types: list[str] = []
        self._datetime = datetime_service
        self._access_control = access_control
        self._capability_envelope = capability_envelope
        self._budget_policy = budget_policy
        self._grants = list(grants) if grants is not None else None
        self._access_policy = access_policy
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
            grants=self._grants,
        )
        self._durable: DurableInstrumentor | None = None
        self._durable_script: DurableScript | None = None
        self._bind_base_dir: Path | None = None

    @property
    def completer(self) -> Completer:
        return self._completer

    @property
    def model(self) -> str:
        return self._model

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    @property
    def judge_provider(self) -> JudgeProvider | None:
        return self._judge_provider

    @property
    def rag_retriever(self) -> Any | None:
        return self._rag_retriever

    @property
    def lifecycle_extensions(self) -> dict[str, Any]:
        return self._lifecycle_extensions

    @property
    def access_control(self) -> AccessControl | None:
        return self._access_control

    @property
    def capability_envelope(self) -> CapabilityEnvelope | None:
        return self._capability_envelope

    @property
    def budget_policy(self) -> BudgetPolicy | None:
        """Host-supplied spend ceiling; ``None`` → unlimited at run sites."""
        return self._budget_policy

    @property
    def grants(self) -> list[object] | None:
        return list(self._grants) if self._grants is not None else None

    @property
    def access_policy(self) -> GrantPolicyLike | None:
        return self._access_policy

    def resolve_budget_policy(
        self,
        *,
        explicit: BudgetPolicy | None = None,
        body_budget: Mapping[str, Any] | None = None,
    ) -> BudgetPolicy:
        """Prefer explicit / body override, else instrumentor default, else unlimited."""
        return resolve_run_budget(
            explicit=explicit,
            runtime_default=self._budget_policy,
            body_budget=body_budget,
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

    @property
    def bind_base_dir(self) -> Path | None:
        return self._bind_base_dir

    @bind_base_dir.setter
    def bind_base_dir(self, value: Path | None) -> None:
        self._bind_base_dir = value

    def configure_durable_session(
        self,
        *,
        graph: str,
        controller: str = "story",
        store: str = "memory",
    ) -> None:
        """Bind durable IoC session knobs before ``start`` / ``answer`` verbs."""
        if store not in {"memory", "shared"}:
            raise ValueError(f"unsupported durable store {store!r}")
        self._durable_script = DurableScript(
            graph=graph,
            controller=controller,
            store=store,
            steps=[],
        )
        self._durable = DurableInstrumentor(self._durable_script)

    def _ensure_durable(self) -> DurableInstrumentor:
        if self._durable is None:
            raise RuntimeError(
                "durable verbs require scenario durable: {graph, controller, store}"
            )
        return self._durable

    def run_durable_start(self, body: StartBody) -> StepObservation:
        return self._ensure_durable().start(body)

    def run_durable_answer(self, body: AnswerBody) -> StepObservation:
        return self._ensure_durable().answer(body)

    def run_durable_inspect(self, body: InspectBody) -> StepObservation:
        return self._ensure_durable().inspect(body)

    def run_durable_rebuild(self, body: RebuildBody) -> StepObservation:
        del body
        return self._ensure_durable().rebuild()

    def run_durable_list_recipes(self, body: ListRecipesBody) -> StepObservation:
        del body
        return self._ensure_durable().list_recipes()

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
        last_fields: dict[str, Any] = {}
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
            if step.fields:
                last_fields = dict(step.fields)
        all_events = self._log.query(agent_id=self._agent_id)
        if not all_events:
            all_events = self._log.query()
        types = [e.type for e in all_events]
        event_dicts = [_event_dict(e) for e in all_events]
        priced = sum(
            float(e.payload.get("units") or 0)
            for e in all_events
            if e.type == "core:cost"
        )
        step_cost = max((float(s.cost_units) for s in steps), default=0.0)
        field_budget = 0.0
        for step in steps:
            raw = step.fields.get("budget_spent")
            if raw is not None:
                field_budget = max(field_budget, float(raw))
        units = max(priced, step_cost, field_budget)
        prompt, completion, total = _token_totals(event_dicts)
        return CliRunResult(
            steps=steps,
            event_types=types,
            tapped_event_types=list(self._tapped_types),
            events=event_dicts,
            cost_units=units,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            text=last_text,
            status=last_status,
            traversal_kinds=last_traversal,
            component_parent_ids=last_parents,
            rounds=last_rounds,
            turns=last_turns,
            recipe_in_catalog=last_in_catalog,
            description_name=last_description,
            subgraph_node_ids=last_subgraph_ids,
            fields=last_fields,
        )

    async def _run_command(self, command: CliParsedCommand) -> CliStepResult:
        verb = self._verbs.get(command.verb)
        if verb is None:
            known = ", ".join(sorted(self._verbs))
            raise KeyError(f"unknown CLI verb {command.verb!r}; known: {known}")
        params = verb.params_model.model_validate(command.params)
        outcome = await verb.run(params, self)
        if isinstance(outcome, CliStepResult):
            return outcome
        if isinstance(outcome, dict):
            return CliStepResult(verb=command.verb, fields=outcome)
        raise TypeError(
            f"verb {command.verb!r} returned {type(outcome).__name__}; "
            "expected CliStepResult or dict"
        )

    async def run_infer(self, body: InferCommand) -> CliStepResult:
        before = len(self._log.query())
        graph = build_cli_universe_graph(prompt=body.prompt, system=body.system)
        if body.model:
            graph.nodes[CLI_INFER_NODE_ID].payload["model"] = body.model
        result = await self._executor.run(
            graph,
            budget_policy=self.resolve_budget_policy(),
        )
        after_events = self._log.query()[before:]
        node = result.graph.nodes.get(CLI_INFER_NODE_ID)
        text = None
        if node is not None:
            text = str((node.payload or {}).get("text") or "") or None
        event_dicts = [_event_dict(e) for e in after_events]
        units = sum(
            float(e.payload.get("units") or 0)
            for e in after_events
            if e.type == "core:cost"
        )
        prompt, completion, total = _token_totals(event_dicts)
        return CliStepResult(
            verb="infer",
            text=text,
            status=result.status,
            event_types=[e.type for e in after_events],
            events=event_dicts,
            cost_units=units,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            clock_iso=self._datetime.now_utc_iso(),
        )

    async def run_tool_loop(self, body: ToolLoopCommand) -> CliStepResult:
        before = len(self._log.query())
        tools = ToolRegistry()
        for definition in self._tools.definitions():
            tools.register(self._tools.get(definition.name))
        if body.tool_name not in tools:
            tools.register(
                Tool(
                    body.tool_name,
                    lambda: "ok",
                    description="cli tool",
                    grants=list(body.tool_grants or []),
                )
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
            harness_family=body.family,
            grants=self._grants,
            access_policy=self._access_policy,
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
        event_dicts = [_event_dict(e) for e in after_events]
        units = sum(
            float(e.payload.get("units") or 0)
            for e in after_events
            if e.type == "core:cost"
        )
        prompt, completion, total = _token_totals(event_dicts)
        permission_denied = any(
            "Permission denied" in (m.content or "") for m in result.messages
        )
        return CliStepResult(
            verb="tool_loop",
            text=result.final_text,
            status="ok" if (result.final_text or "").strip() else "failed",
            event_types=[e.type for e in after_events],
            events=event_dicts,
            cost_units=units,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            clock_iso=self._datetime.now_utc_iso(),
            traversal_kinds=kinds,
            component_parent_ids=parents,
            fields={
                "permission_denied": permission_denied,
                "allowed": not permission_denied and bool((result.final_text or "").strip()),
            },
        )

    async def run_recipe(self, body: RunRecipeCommand) -> CliStepResult:
        adapter = self._recipe_adapters.get(body.name)
        if adapter is None:
            known = ", ".join(sorted(self._recipe_adapters))
            raise KeyError(
                f"run_recipe has no adapter for {body.name!r}; known: {known}"
            )
        return cast(CliStepResult, await adapter.run(body, self))

    async def instantiate_recipe(self, body: InstantiateRecipeCommand) -> CliStepResult:
        """:class:`~mechaharness.recipe_bind.RecipeBind` → concrete graph."""
        from mechaharness.recipe_bind import observe_instantiated_recipe
        from mechaharness.recipe_runner import instantiate_recipe as expand_recipe

        bind = body.resolve_bind(base_dir=self._bind_base_dir)
        template, materialized = bind.resolve_template()
        graph = expand_recipe(materialized.name, materialized.to_params())
        observed = observe_instantiated_recipe(materialized, graph, template)
        return CliStepResult(
            verb="instantiate_recipe",
            status="ok",
            clock_iso=self._datetime.now_utc_iso(),
            recipe_in_catalog=bool(observed["recipe_in_catalog"]),
            subgraph_node_ids=list(observed["subgraph_node_ids"]),
            fields=dict(observed["fields"]),
        )

    async def tile_recipe(self, body: TileRecipeCommand) -> CliStepResult:
        """:class:`~mechaharness.recipe_bind.RecipeTileBind` → tiled observation."""
        tile = body.resolve_bind(base_dir=self._bind_base_dir)
        fields = tile.tile()
        return CliStepResult(
            verb="tile_recipe",
            status="ok",
            clock_iso=self._datetime.now_utc_iso(),
            fields=fields,
        )

    async def recipe_plan(self, body: RecipePlanCommand) -> CliStepResult:
        """Run a lifecycle / composition plan document."""
        import inspect

        fields = body.resolve_and_run(base_dir=self._bind_base_dir)
        if inspect.isawaitable(fields):
            fields = await fields
        return CliStepResult(
            verb="recipe_plan",
            status="ok",
            clock_iso=self._datetime.now_utc_iso(),
            fields=dict(fields),
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

    async def run_set_clock(self, body: SetClockCommand) -> CliStepResult:
        self._set_clock(body.at)
        return CliStepResult(
            verb="set_clock",
            clock_iso=self._datetime.now_utc_iso(),
        )

    async def run_advance_clock(self, body: AdvanceClockCommand) -> CliStepResult:
        self._advance_clock(body)
        return CliStepResult(
            verb="advance_clock",
            clock_iso=self._datetime.now_utc_iso(),
        )


def script_from_mapping(data: dict[str, Any]) -> CliScript:
    """Build a product script from a YAML-like mapping."""
    return _script_from_mapping(data)


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


def _token_totals(events: Sequence[Mapping[str, Any]]) -> tuple[int, int, int]:
    """Sum ``usage`` from ``core:inference`` event payloads."""
    prompt = 0
    completion = 0
    total = 0
    for event in events:
        if event.get("type") != "core:inference":
            continue
        payload = event.get("payload") or {}
        if not isinstance(payload, Mapping):
            continue
        usage = payload.get("usage") or {}
        if not isinstance(usage, Mapping):
            continue
        p = usage.get("prompt_tokens")
        c = usage.get("completion_tokens")
        t = usage.get("total_tokens")
        prompt += int(p) if p is not None else 0
        completion += int(c) if c is not None else 0
        if t is not None:
            total += int(t)
        else:
            total += (int(p) if p is not None else 0) + (
                int(c) if c is not None else 0
            )
    return prompt, completion, total


def _merge_cost_observation(data: dict[str, Any]) -> dict[str, Any]:
    """Prefer the higher of priced ``cost_units`` and graph ``budget_spent``."""
    priced = float(data.get("cost_units") or 0)
    budget = data.get("budget_spent")
    if budget is not None:
        data["cost_units"] = max(priced, float(budget))
    return data


__all__ = [
    "AdvanceClockCommand",
    "CliInstrumentor",
    "CliParsedCommand",
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
