"""Persona-task YAML: environment → graph → steps → complete → cleanup.

Wraps product :class:`~mechaharness.cli_instrumentor.CliInstrumentor` verbs.
No probe path; Config knobs come only from ``environment`` / ``graph``.
"""

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
from tests.stories.scenarios.cli_scenario import _require_cost_ceiling


class EnvironmentBlock(BaseModel):
    """Host Config surface for this story (family, backend, optional clock)."""

    model_config = ConfigDict(extra="forbid")

    family: str = "pass_through"
    backend: str = "mock"
    # ISO-8601 instant for MockDateTimeService; omit for harness default.
    clock: str | None = None


class DurableGraphBlock(BaseModel):
    """Durable IoC session knobs when ``graph.recipe`` is run via start/answer."""

    model_config = ConfigDict(extra="forbid")

    controller: str = "story"
    store: Literal["memory", "shared"] = "memory"


class GraphBlock(BaseModel):
    """What plan/session the persona loads before walking steps."""

    model_config = ConfigDict(extra="forbid")

    recipe: str | None = None
    bind: str | None = None
    durable: DurableGraphBlock | None = None

    @model_validator(mode="after")
    def _durable_needs_recipe(self) -> GraphBlock:
        if self.durable is not None and not self.recipe:
            raise ValueError("graph.durable requires graph.recipe")
        return self


class StoryStep(BaseModel):
    """One action (product verb) with optional mid-walk expects."""

    model_config = ConfigDict(extra="forbid")

    do: dict[str, Any]
    expect: list[dict[str, Any]] | None = None
    expect_error: str | None = None

    @model_validator(mode="after")
    def _one_verb_no_probe(self) -> StoryStep:
        if "probe" in self.do:
            raise ValueError("user_story steps must not use probe; use product verbs")
        if len(self.do) != 1:
            raise ValueError(
                f"step.do needs exactly one verb key; got {sorted(self.do)}"
            )
        verb = next(iter(self.do))
        if verb == "set_clock" or verb == "advance_clock":
            raise ValueError(
                f"{verb!r} belongs in environment.clock, not steps"
            )
        return self

    def to_command(self) -> CliParsedCommand:
        raw = dict(self.do)
        if self.expect is not None:
            raw["expect"] = self.expect
        if self.expect_error is not None:
            raw["expect_error"] = self.expect_error
        return parse_cli_commands([raw])[0]


class CompleteBlock(BaseModel):
    """Story-completion claims (what the persona verifies when the job is done)."""

    model_config = ConfigDict(extra="forbid")

    expect: list[CliAssertionSpec] = Field(min_length=1)


class UserStoryScenario(BaseModel):
    """Structured persona task: environment, optional graph, steps, complete."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["user_story"]
    environment: EnvironmentBlock
    graph: GraphBlock | None = None
    steps: list[StoryStep] = Field(min_length=1)
    complete: CompleteBlock
    cleanup: list[Any] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _parse_complete_expect(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        complete = out.get("complete")
        if isinstance(complete, dict) and isinstance(complete.get("expect"), list):
            complete = dict(complete)
            complete["expect"] = parse_expect_list(complete["expect"])
            out["complete"] = complete
        return out

    @model_validator(mode="after")
    def _cleanup_empty(self) -> UserStoryScenario:
        if self.cleanup:
            raise ValueError(
                "cleanup is reserved; leave cleanup: [] until cleanup verbs exist"
            )
        return self

    def to_script(self) -> CliScript:
        return CliScript(commands=[step.to_command() for step in self.steps])

    def assert_expect(
        self,
        result: CliRunResult,
        assertions: dict[str, CliAssertion],
        *,
        label: str,
    ) -> None:
        commands = [s.to_command() for s in self.steps]
        if len(result.steps) != len(commands):
            raise AssertionError(
                f"{label}: got {len(result.steps)} steps for "
                f"{len(commands)} story steps"
            )
        for index, (cmd, step) in enumerate(zip(commands, result.steps)):
            step_label = f"{label}:steps[{index}].{cmd.verb}"
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
        complete_label = f"{label}:complete"
        check_assertions(
            result.observation(),
            self.complete.expect,
            assertions,
            label=complete_label,
        )
        _require_cost_ceiling(
            result.observation(), self.complete.expect, label=complete_label
        )


def load_user_story_scenario(path: Path) -> UserStoryScenario:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: scenario root must be a mapping")
    try:
        return UserStoryScenario.model_validate(data)
    except Exception as exc:
        raise ValueError(f"{path}: invalid user_story scenario: {exc}") from exc


async def run_user_story_scenario(
    scenario: UserStoryScenario,
    instrumentor: CliInstrumentor,
) -> CliRunResult:
    graph = scenario.graph
    if graph is not None and graph.durable is not None:
        assert graph.recipe is not None
        instrumentor.configure_durable_session(
            graph=graph.recipe,
            controller=graph.durable.controller,
            store=graph.durable.store,
        )
    elif graph is not None and graph.bind is not None:
        # Shape-only setup: expand RecipeBind before walking product steps.
        setup = CliScript(
            commands=[
                CliParsedCommand(
                    verb="instantiate_recipe",
                    params={"path": graph.bind},
                )
            ]
        )
        await instrumentor.run(setup)
    return await instrumentor.run(scenario.to_script())


__all__ = [
    "CompleteBlock",
    "DurableGraphBlock",
    "EnvironmentBlock",
    "GraphBlock",
    "StoryStep",
    "UserStoryScenario",
    "load_user_story_scenario",
    "run_user_story_scenario",
]
