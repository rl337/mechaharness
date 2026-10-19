"""Host CLI instrumentor over the concrete ``cli_universe`` graph.

Verb-led commands (``infer``, ``set_clock``, ``advance_clock``) with optional
parameterization and good defaults. Story YAML may attach test-only ``expect``
blocks; this module returns observations and does not assert.

See ``docs/reference/cli-universe.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pyiv.time import DateTimeService, MockDateTimeService

from mechaharness.budget import BudgetPolicy
from mechaharness.cli_infer_runner import CliInferRunner
from mechaharness.cli_universe import CLI_INFER_NODE_ID, build_cli_universe_graph
from mechaharness.core.access import CostAccountant, InMemoryCostAccountant
from mechaharness.core.completer import Completer
from mechaharness.core.events import (
    AgentRef,
    Event,
    EventLog,
    EventTypeRef,
    InMemoryEventLog,
)
from mechaharness.graph_executor import GraphNodeRunnerRegistry
from mechaharness.host_kit import host_graph_executor


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
    set_clock: SetClockCommand | None = None
    advance_clock: AdvanceClockCommand | None = None

    @model_validator(mode="after")
    def _one_verb(self) -> CliCommand:
        verbs = [
            ("infer", self.infer),
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
        if self.infer is not None:
            return "infer"
        if self.set_clock is not None:
            return "set_clock"
        return "advance_clock"


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

    def as_expect_dict(self) -> dict[str, Any]:
        return {
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
        }


class CliRunResult(BaseModel):
    """Full script run: per-command steps plus aggregate event view."""

    model_config = ConfigDict(extra="forbid")

    steps: list[CliStepResult] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    cost_units: float = 0.0
    text: str | None = None

    def as_expect_dict(self) -> dict[str, Any]:
        return {
            "event_types": list(self.event_types),
            "event_types_exactly": list(self.event_types),
            "cost_units": self.cost_units,
            "units_positive": self.cost_units > 0,
            "text": self.text,
            "text_nonempty": bool(self.text and str(self.text).strip()),
            "inference_ts": _first_ts(self.events, "core:inference"),
            "cost_ts": _first_ts(self.events, "core:cost"),
        }


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
    ) -> None:
        self._completer = completer
        self._model = model
        self._agent_id = agent_id
        self._raw_log = event_log or InMemoryEventLog()
        self._datetime: DateTimeService = datetime_service or MockDateTimeService(
            datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        )
        self._log: EventLog = StampingEventLog(self._raw_log, self._datetime)
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

    async def run(self, script: CliScript) -> CliRunResult:
        steps: list[CliStepResult] = []
        last_text: str | None = None
        for command in script.commands:
            step = await self._run_command(command)
            steps.append(step)
            if step.text is not None:
                last_text = step.text
        all_events = self._log.query(agent_id=self._agent_id)
        types = [e.type for e in all_events]
        units = sum(
            float(e.payload.get("units") or 0)
            for e in all_events
            if e.type == "core:cost"
        )
        return CliRunResult(
            steps=steps,
            event_types=types,
            events=[_event_dict(e) for e in all_events],
            cost_units=units,
            text=last_text,
        )

    async def _run_command(self, command: CliCommand) -> CliStepResult:
        before = len(self._log.query(agent_id=self._agent_id))
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
        assert command.infer is not None
        body = command.infer
        graph = build_cli_universe_graph(prompt=body.prompt, system=body.system)
        if body.model:
            graph.nodes[CLI_INFER_NODE_ID].payload["model"] = body.model
        result = await self._executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
        )
        after_events = self._log.query(agent_id=self._agent_id)[before:]
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
    "SetClockCommand",
    "StampingEventLog",
    "script_from_mapping",
]
