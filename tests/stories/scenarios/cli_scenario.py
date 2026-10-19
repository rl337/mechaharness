"""Story YAML tests over the product CLI instrumentor."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.cli_acceptance_verbs import (
    CheckCompleterFlavorsCommand,
    CheckInferenceCaptureCommand,
    HostKitSubmitOnceCommand,
    JudgeRouteCommand,
)
from mechaharness.cli_diagnostic_verbs import (
    CheckModelAffinityCommand,
    CompareRunParityCommand,
    ReplayModelInputCommand,
    RouteCapabilitiesCommand,
    ShadowDecisionBackendsCommand,
)
from mechaharness.cli_graph_verbs import (
    BoundedRepairLoopCommand,
    ConvergenceCeilingCommand,
    GraphEventCorrelatorsCommand,
    GraphExecutorRunCommand,
    GraphLinkagePreflightCommand,
    GraphTransitionInspectCommand,
    RolloutGraphBuildCommand,
    TargetedRollbackSelectCommand,
    TopologyEfficiencyCommand,
    ValidatorQualificationCommand,
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
    default_is_inference: bool | None = None
    flavor_selected: bool | None = None
    matched_selects_flavor: bool | None = None
    linkage_ok: bool | None = None
    codes_exactly: list[str] | None = None
    scenario_results_exactly: dict[str, Any] | None = None
    route_selected: str | None = None
    verdict: str | None = None
    answer_count: int | None = None
    total_node_work_ms: float | None = None
    elapsed_ms: float | None = None
    work_exceeds_elapsed: bool | None = None
    notes_exactly: list[str] | None = None
    honest_qualified: bool | None = None
    weak_qualified: bool | None = None
    final_status: str | None = None
    consume_sum: int | None = None
    emitted_graph_start: bool | None = None
    emitted_graph_end: bool | None = None
    denied_without_execute_grant: bool | None = None
    flaky_attempts: int | None = None
    graph_events_have_graph_id: bool | None = None
    node_events_have_node_id: bool | None = None
    recipe: list[list[str]] | None = None
    epochs: list[int] | None = None
    child_parent_run_ids: list[str] | None = None
    child_nest_depths: list[int] | None = None
    node_attempt_rows: list[list[Any]] | None = None
    missing_runner_ok: bool | None = None
    missing_runner_codes_exactly: list[str] | None = None
    missing_stop_ok: bool | None = None
    missing_stop_codes_exactly: list[str] | None = None
    ok_linear_ok: bool | None = None
    ok_linear_fingerprint_nonempty: bool | None = None
    issues: list[Any] | None = None
    verify_kinds_exactly: list[str] | None = None
    rollback_target: str | None = None
    repair_target: str | None = None
    roots_exactly: list[str] | None = None
    retry_linked: bool | None = None
    terminal: str | None = None
    reason: str | None = None
    success: bool | None = None

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
    check_completer_flavors: CheckCompleterFlavorsCommand | None = None
    check_inference_capture: CheckInferenceCaptureCommand | None = None
    host_kit_submit_once: HostKitSubmitOnceCommand | None = None
    judge_route: JudgeRouteCommand | None = None
    topology_efficiency: TopologyEfficiencyCommand | None = None
    validator_qualification: ValidatorQualificationCommand | None = None
    bounded_repair_loop: BoundedRepairLoopCommand | None = None
    graph_executor_run: GraphExecutorRunCommand | None = None
    graph_event_correlators: GraphEventCorrelatorsCommand | None = None
    graph_linkage_preflight: GraphLinkagePreflightCommand | None = None
    graph_transition_inspect: GraphTransitionInspectCommand | None = None
    targeted_rollback_select: TargetedRollbackSelectCommand | None = None
    rollout_graph_build: RolloutGraphBuildCommand | None = None
    convergence_ceiling: ConvergenceCeilingCommand | None = None
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
            self.check_completer_flavors,
            self.check_inference_capture,
            self.host_kit_submit_once,
            self.judge_route,
            self.topology_efficiency,
            self.validator_qualification,
            self.bounded_repair_loop,
            self.graph_executor_run,
            self.graph_event_correlators,
            self.graph_linkage_preflight,
            self.graph_transition_inspect,
            self.targeted_rollback_select,
            self.rollout_graph_build,
            self.convergence_ceiling,
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
