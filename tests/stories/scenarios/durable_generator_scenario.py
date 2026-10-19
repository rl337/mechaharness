"""Story YAML tests over the product durable generator instrumentor.

YAML = human-readable script + per-step hard expects. The pytest harness only
loads, runs :class:`DurableInstrumentor`, and asserts. Incomplete stanzas fail
at load time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.durable_generator_script import (
    AnswerBody,
    DurableInstrumentor,
    DurableScript,
    InspectBody,
    ListRecipesBody,
    RebuildBody,
    ScriptError,
    StartBody,
    StepObservation,
    script_from_mapping,
)
from mechaharness.durable_graph_generator import YieldKind


class StepExpect(BaseModel):
    """Hard checks for one step observation (closed key set)."""

    model_config = ConfigDict(extra="forbid")

    kind: YieldKind | None = None
    sequence: int | None = None
    question: str | None = None
    pending_question: str | None = None
    pending_cleared: bool | None = None
    phase: str | None = None
    same_request_id: bool | None = None
    guidance_yields: int | None = None
    resumes: int | None = None
    local_steps: int | None = None
    recipe_listed: bool | None = None
    recipes: list[str] | None = None
    controller: str | None = None
    controller_ok: bool | None = None
    same_sequence: bool | None = None
    separate_calls: bool | None = None
    request_id: str | None = None

    @model_validator(mode="after")
    def _at_least_one_key(self) -> StepExpect:
        if not self.model_dump(exclude_none=True):
            raise ValueError("expect must declare at least one key")
        return self

    def declared(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ScenarioStep(BaseModel):
    """One script verb plus optional hard expect / expect_error."""

    model_config = ConfigDict(extra="forbid")

    start: StartBody | None = None
    answer: AnswerBody | None = None
    inspect: InspectBody | None = None
    rebuild: RebuildBody | None = None
    list_recipes: ListRecipesBody | None = None
    expect: StepExpect | None = None
    expect_error: ScriptError | None = None

    @model_validator(mode="after")
    def _verb_and_check(self) -> ScenarioStep:
        verbs = [
            self.start,
            self.answer,
            self.inspect,
            self.rebuild,
            self.list_recipes,
        ]
        if sum(1 for v in verbs if v is not None) != 1:
            raise ValueError(
                "each step needs exactly one of start/answer/inspect/"
                "rebuild/list_recipes"
            )
        if self.expect is None and self.expect_error is None:
            if self.rebuild is None:
                raise ValueError(
                    "each step needs expect or expect_error "
                    "(rebuild may omit both)"
                )
        if self.expect is not None and self.expect_error is not None:
            raise ValueError("step cannot set both expect and expect_error")
        return self


class DurableScenario(BaseModel):
    """Complete durable-generator story: product script fields + step expects."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["durable_generator"]
    graph: str
    controller: str = "story"
    store: Literal["memory", "shared"] = "memory"
    steps: list[ScenarioStep] = Field(min_length=1)

    def to_script(self) -> DurableScript:
        return script_from_mapping(self.model_dump(exclude={"kind"}))

    def run(self) -> list[StepObservation]:
        return DurableInstrumentor(self.to_script()).run()

    def assert_expects(
        self,
        observations: list[StepObservation],
        *,
        label: str,
    ) -> None:
        if len(observations) != len(self.steps):
            raise AssertionError(
                f"{label}: got {len(observations)} observations for "
                f"{len(self.steps)} steps"
            )
        for i, (step, obs) in enumerate(zip(self.steps, observations)):
            step_label = f"{label} step[{i}]"
            got = obs.as_expect_dict()
            if step.expect_error is not None:
                assert got.get("error") == step.expect_error, (
                    f"{step_label}: expect_error {step.expect_error!r} "
                    f"!= {got.get('error')!r}"
                )
                continue
            if step.expect is None:
                continue
            for key, wanted in step.expect.declared().items():
                if key not in got:
                    raise AssertionError(
                        f"{step_label}: missing actual key {key!r}; "
                        f"got {sorted(got)}"
                    )
                assert got[key] == wanted, (
                    f"{step_label}: {key}: {got[key]!r} != {wanted!r}"
                )


def load_durable_scenario(path: Path) -> DurableScenario:
    """Parse and validate a ``scenario.yaml``; raise on incomplete stanzas."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: scenario root must be a mapping")
    # Accept legacy ``recipe`` as ``graph``.
    if "graph" not in data and "recipe" in data:
        data = {**data, "graph": data["recipe"]}
    try:
        return DurableScenario.model_validate(data)
    except Exception as exc:
        raise ValueError(f"{path}: invalid durable scenario: {exc}") from exc
