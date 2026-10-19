"""Story YAML tests over the product CLI instrumentor."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.cli_diagnostic_verbs import (
    CheckModelAffinityCommand,
    CompareRunParityCommand,
    ReplayModelInputCommand,
    RouteCapabilitiesCommand,
    ShadowDecisionBackendsCommand,
)
from mechaharness.cli_instrumentor import (
    AdvanceClockCommand,
    CliInstrumentor,
    CliRunResult,
    InferCommand,
    RunRecipeCommand,
    SetClockCommand,
    ToolLoopCommand,
    script_from_mapping,
)


class CliExpect(BaseModel):
    """Hard checks against a CLI run (closed key set)."""

    model_config = ConfigDict(extra="forbid")

    event_types_exactly: list[str] | None = None
    tapped_event_types_exactly: list[str] | None = None
    units_positive: bool | None = None
    text_nonempty: bool | None = None
    text: str | None = None
    status: str | None = None
    inference_ts: str | None = None
    cost_ts: str | None = None
    cost_units: float | None = None
    traversal_kinds_exactly: list[str] | None = None
    component_parents_exactly: list[str] | None = None
    rounds: int | None = None
    turns: int | None = None
    recipe_in_catalog: bool | None = None
    description_name: str | None = None
    subgraph_node_ids_exactly: list[str] | None = None
    graph_node_ids_exactly: list[str] | None = None
    hashes_ok: bool | None = None
    reconstructed_equals: bool | None = None
    manifest_ref_nonempty: bool | None = None
    selected_model_class: str | None = None
    selected_lane: str | None = None
    uncalibrated_is_null: bool | None = None
    comparable: bool | None = None
    material_mismatches_exactly: list[str] | None = None
    unavailable_exactly: list[str] | None = None
    available_exactly: list[str] | None = None
    matched_actions_exactly: list[str] | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> CliExpect:
        if not self.model_dump(exclude_none=True):
            raise ValueError("expect must declare at least one key")
        return self

    def declared(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class CliScenarioCommand(BaseModel):
    """CLI verb plus optional per-command expect."""

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
    expect: CliExpect | None = None

    @model_validator(mode="after")
    def _one_verb(self) -> CliScenarioCommand:
        verbs = [
            self.infer,
            self.tool_loop,
            self.run_recipe,
            self.replay_model_input,
            self.route_capabilities,
            self.check_model_affinity,
            self.compare_run_parity,
            self.shadow_decision_backends,
            self.set_clock,
            self.advance_clock,
        ]
        if sum(1 for v in verbs if v is not None) != 1:
            raise ValueError("each command needs exactly one CLI verb")
        return self


class CliScenario(BaseModel):
    """Complete CLI story script: product commands + hard expect."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["cli"]
    commands: list[CliScenarioCommand] = Field(min_length=1)
    expect: CliExpect

    def to_script(self):
        return script_from_mapping(self.model_dump(exclude={"kind", "expect"}))

    def assert_expect(self, result: CliRunResult, *, label: str) -> None:
        got = result.as_expect_dict()
        for key, wanted in self.expect.declared().items():
            if key not in got:
                raise AssertionError(
                    f"{label}: missing actual key {key!r}; got {sorted(got)}"
                )
            assert got[key] == wanted, f"{label}: {key}: {got[key]!r} != {wanted!r}"


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
    return await instrumentor.run(scenario.to_script())
