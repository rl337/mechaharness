"""Story YAML tests over the product CLI instrumentor."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.cli_assertion import (
    CliAssertion,
    CliAssertionSpec,
    check_assertions,
    parse_expect_list,
)
from mechaharness.cli_instrumentor import CliInstrumentor, CliRunResult
from mechaharness.cli_verb import CliParsedCommand, CliScript, parse_cli_commands


class DurableSessionBlock(BaseModel):
    """Scenario-level durable IoC session (graph / controller / store)."""

    model_config = ConfigDict(extra="forbid")

    graph: str
    controller: str = "story"
    store: Literal["memory", "shared"] = "memory"


class CliScenario(BaseModel):
    """CLI story script: verb commands + open structured expect list."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["cli"]
    commands: list[CliParsedCommand] = Field(min_length=1)
    expect: list[CliAssertionSpec] | None = None
    durable: DurableSessionBlock | None = None

    @model_validator(mode="before")
    @classmethod
    def _parse_commands_and_expect(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        raw = out.get("commands")
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            if "verb" not in raw[0]:
                out["commands"] = parse_cli_commands(raw)
        expect = out.get("expect")
        if isinstance(expect, list):
            out["expect"] = parse_expect_list(expect)
        commands = out.get("commands") or []
        for cmd in commands:
            if isinstance(cmd, CliParsedCommand) and cmd.expect is not None:
                # already parsed as list[dict] by parse_cli_commands
                continue
        return out

    @model_validator(mode="after")
    def _expect_present(self) -> CliScenario:
        has_script_expect = bool(self.expect)
        has_step_expect = any(
            c.expect is not None or c.expect_error is not None for c in self.commands
        )
        if not has_script_expect and not has_step_expect:
            raise ValueError(
                "scenario needs script-level expect or per-command expect/expect_error"
            )
        return self

    def to_script(self) -> CliScript:
        return CliScript(commands=self.commands)

    def assert_expect(
        self,
        result: CliRunResult,
        assertions: dict[str, CliAssertion],
        *,
        label: str,
    ) -> None:
        if len(result.steps) != len(self.commands):
            raise AssertionError(
                f"{label}: got {len(result.steps)} steps for "
                f"{len(self.commands)} commands"
            )
        for index, (cmd, step) in enumerate(zip(self.commands, result.steps)):
            step_label = f"{label}:commands[{index}].{cmd.verb}"
            obs = step.observation()
            if cmd.expect_error is not None:
                if obs.get("error") != cmd.expect_error:
                    raise AssertionError(
                        f"{step_label}: expect_error {cmd.expect_error!r} "
                        f"!= {obs.get('error')!r}"
                    )
            elif cmd.expect is not None:
                specs = parse_expect_list(cmd.expect)
                check_assertions(obs, specs, assertions, label=step_label)
        if self.expect:
            check_assertions(
                result.observation(),
                self.expect,
                assertions,
                label=label,
            )
            _require_cost_ceiling(
                result.observation(), self.expect, label=label
            )


def _require_cost_ceiling(
    observation: dict[str, Any],
    specs: list[CliAssertionSpec],
    *,
    label: str,
) -> None:
    """Graph executions must declare a cost_units / budget_spent ceiling."""
    if "budget_spent" not in observation:
        return
    covered = False
    for spec in specs:
        params = spec.params()
        if params.get("key") not in {"cost_units", "budget_spent"}:
            continue
        if spec.kind in {"lte", "equals", "gte", "positive"}:
            covered = True
            break
    if not covered:
        raise AssertionError(
            f"{label}: graph execution exposed budget_spent="
            f"{observation.get('budget_spent')!r} but expect has no "
            "lte/equals/gte/positive on cost_units or budget_spent"
        )


def load_cli_scenario(path: Path) -> CliScenario:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: scenario root must be a mapping")
    try:
        return CliScenario.model_validate(data)
    except Exception as exc:
        raise ValueError(f"{path}: invalid cli scenario: {exc}") from exc


async def run_cli_scenario(
    scenario: CliScenario,
    instrumentor: CliInstrumentor,
) -> CliRunResult:
    if scenario.durable is not None:
        instrumentor.configure_durable_session(
            graph=scenario.durable.graph,
            controller=scenario.durable.controller,
            store=scenario.durable.store,
        )
    return await instrumentor.run(scenario.to_script())
