"""Map-multibind contributions for story acceptance probes."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, Union, cast

from pydantic import BaseModel

from mechaharness.cli_verb import CliProbe
from tests.stories.cli_probes.acceptance_verbs import (
    CheckCompleterFlavorsCommand,
    CheckInferenceCaptureCommand,
    HostKitSubmitOnceCommand,
    run_check_completer_flavors,
    run_check_inference_capture,
    run_host_kit_submit_once,
)
from tests.stories.cli_probes.decision_plane_probes import (
    ActionSafetyCaseCommand,
    CitationSupportCaseCommand,
    ContextBudgetCaseCommand,
    DecisionPlaneModelPolicyCommand,
    DecisionPlanePolicyCaseCommand,
    DecisionPlaneProjectionCommand,
    DecisionPlaneRecipeCommand,
    DecisionPlaneShadowCommand,
    DecisionPlaneShadowCompareCommand,
    DecisionPlaneTelemetryCommand,
    DecisionSurfaceRejectCommand,
    FixtureJudgeBatchCommand,
    OfflineDecisionExportCommand,
    PolicyReplayCommand,
    RequirementsGapCaseCommand,
    TaskRouteCaseCommand,
    run_action_safety_case,
    run_citation_support_case,
    run_context_budget_case,
    run_decision_plane_model_policy,
    run_decision_plane_policy_case,
    run_decision_plane_projection,
    run_decision_plane_recipe,
    run_decision_plane_shadow,
    run_decision_plane_shadow_compare,
    run_decision_plane_telemetry,
    run_decision_surface_reject,
    run_fixture_judge_batch,
    run_offline_decision_export,
    run_policy_replay,
    run_requirements_gap_case,
    run_task_route_case,
)
from tests.stories.cli_probes.graph_verbs import (
    BoundedRepairLoopCommand,
    CheckpointFingerprintRefuseCommand,
    ConvergenceCeilingCommand,
    DecisionConflictNeighborRevisitCommand,
    DynamicSubgraphNestCommand,
    EnvironmentLinkageFailCommand,
    GraphBudgetLimitsCommand,
    GraphBudgetSubgraphRollupCommand,
    GraphEventCorrelatorsCommand,
    GraphExecutorRunCommand,
    GraphLinkagePreflightCommand,
    GraphTransitionInspectCommand,
    LocalPlanResumeCommand,
    RolloutGraphBuildCommand,
    TargetedRollbackSelectCommand,
    TopologyEfficiencyCommand,
    TransactionalDurableResumeCommand,
    ValidatorQualificationCommand,
    WakeReresolveResumeCommand,
    run_bounded_repair_loop,
    run_checkpoint_fingerprint_refuse,
    run_convergence_ceiling,
    run_decision_conflict_neighbor_revisit,
    run_dynamic_subgraph_nest,
    run_environment_linkage_fail,
    run_graph_budget_limits,
    run_graph_budget_subgraph_rollup,
    run_graph_event_correlators,
    run_graph_executor_run,
    run_graph_linkage_preflight,
    run_graph_transition_inspect,
    run_local_plan_resume,
    run_rollout_graph_build,
    run_targeted_rollback_select,
    run_topology_efficiency,
    run_transactional_durable_resume,
    run_validator_qualification,
    run_wake_reresolve_resume,
)
from tests.stories.cli_probes.pure_api_probes import pure_api_cli_probe_classes

ParamsT = TypeVar("ParamsT", bound=BaseModel)
ProbeFn = Callable[[Any], Union[dict[str, Any], Awaitable[dict[str, Any]]]]


def _probe(
    name: str,
    params_model: type[ParamsT],
    fn: ProbeFn,
) -> type[CliProbe]:
    """Story-local probe class (keeps handlers as functions until further split)."""

    class _P(CliProbe):
        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            del runtime
            out = fn(cast(ParamsT, params))
            if inspect.isawaitable(out):
                out = await out
            return out

    _P.name = name
    _P.params_model = params_model
    _P.__name__ = f"{name}_probe"
    _P.__qualname__ = _P.__name__
    return _P


def story_cli_probe_classes() -> dict[str, type[CliProbe]]:
    """Acceptance probes merged into test Config via ``cli_probe_classes()``."""
    probes: dict[str, type[CliProbe]] = {
        "check_completer_flavors": _probe(
            "check_completer_flavors",
            CheckCompleterFlavorsCommand,
            run_check_completer_flavors,
        ),
        "check_inference_capture": _probe(
            "check_inference_capture",
            CheckInferenceCaptureCommand,
            run_check_inference_capture,
        ),
        "host_kit_submit_once": _probe(
            "host_kit_submit_once",
            HostKitSubmitOnceCommand,
            run_host_kit_submit_once,
        ),
        "topology_efficiency": _probe(
            "topology_efficiency",
            TopologyEfficiencyCommand,
            run_topology_efficiency,
        ),
        "validator_qualification": _probe(
            "validator_qualification",
            ValidatorQualificationCommand,
            run_validator_qualification,
        ),
        "bounded_repair_loop": _probe(
            "bounded_repair_loop",
            BoundedRepairLoopCommand,
            run_bounded_repair_loop,
        ),
        "graph_executor_run": _probe(
            "graph_executor_run",
            GraphExecutorRunCommand,
            run_graph_executor_run,
        ),
        "graph_event_correlators": _probe(
            "graph_event_correlators",
            GraphEventCorrelatorsCommand,
            run_graph_event_correlators,
        ),
        "graph_linkage_preflight": _probe(
            "graph_linkage_preflight",
            GraphLinkagePreflightCommand,
            run_graph_linkage_preflight,
        ),
        "graph_transition_inspect": _probe(
            "graph_transition_inspect",
            GraphTransitionInspectCommand,
            run_graph_transition_inspect,
        ),
        "targeted_rollback_select": _probe(
            "targeted_rollback_select",
            TargetedRollbackSelectCommand,
            run_targeted_rollback_select,
        ),
        "rollout_graph_build": _probe(
            "rollout_graph_build",
            RolloutGraphBuildCommand,
            run_rollout_graph_build,
        ),
        "convergence_ceiling": _probe(
            "convergence_ceiling",
            ConvergenceCeilingCommand,
            run_convergence_ceiling,
        ),
        "local_plan_resume": _probe(
            "local_plan_resume",
            LocalPlanResumeCommand,
            run_local_plan_resume,
        ),
        "dynamic_subgraph_nest": _probe(
            "dynamic_subgraph_nest",
            DynamicSubgraphNestCommand,
            run_dynamic_subgraph_nest,
        ),
        "checkpoint_fingerprint_refuse": _probe(
            "checkpoint_fingerprint_refuse",
            CheckpointFingerprintRefuseCommand,
            run_checkpoint_fingerprint_refuse,
        ),
        "environment_linkage_fail": _probe(
            "environment_linkage_fail",
            EnvironmentLinkageFailCommand,
            run_environment_linkage_fail,
        ),
        "wake_reresolve_resume": _probe(
            "wake_reresolve_resume",
            WakeReresolveResumeCommand,
            run_wake_reresolve_resume,
        ),
        "graph_budget_limits": _probe(
            "graph_budget_limits",
            GraphBudgetLimitsCommand,
            run_graph_budget_limits,
        ),
        "graph_budget_subgraph_rollup": _probe(
            "graph_budget_subgraph_rollup",
            GraphBudgetSubgraphRollupCommand,
            run_graph_budget_subgraph_rollup,
        ),
        "transactional_durable_resume": _probe(
            "transactional_durable_resume",
            TransactionalDurableResumeCommand,
            run_transactional_durable_resume,
        ),
        "decision_conflict_neighbor_revisit": _probe(
            "decision_conflict_neighbor_revisit",
            DecisionConflictNeighborRevisitCommand,
            run_decision_conflict_neighbor_revisit,
        ),
        "fixture_judge_batch": _probe(
            "fixture_judge_batch",
            FixtureJudgeBatchCommand,
            run_fixture_judge_batch,
        ),
        "decision_surface_reject": _probe(
            "decision_surface_reject",
            DecisionSurfaceRejectCommand,
            run_decision_surface_reject,
        ),
        "offline_decision_export": _probe(
            "offline_decision_export",
            OfflineDecisionExportCommand,
            run_offline_decision_export,
        ),
        "policy_replay": _probe(
            "policy_replay", PolicyReplayCommand, run_policy_replay
        ),
        "decision_plane_recipe": _probe(
            "decision_plane_recipe",
            DecisionPlaneRecipeCommand,
            run_decision_plane_recipe,
        ),
        "decision_plane_projection": _probe(
            "decision_plane_projection",
            DecisionPlaneProjectionCommand,
            run_decision_plane_projection,
        ),
        "decision_plane_policy_case": _probe(
            "decision_plane_policy_case",
            DecisionPlanePolicyCaseCommand,
            run_decision_plane_policy_case,
        ),
        "decision_plane_shadow": _probe(
            "decision_plane_shadow",
            DecisionPlaneShadowCommand,
            run_decision_plane_shadow,
        ),
        "decision_plane_telemetry": _probe(
            "decision_plane_telemetry",
            DecisionPlaneTelemetryCommand,
            run_decision_plane_telemetry,
        ),
        "decision_plane_model_policy": _probe(
            "decision_plane_model_policy",
            DecisionPlaneModelPolicyCommand,
            run_decision_plane_model_policy,
        ),
        "decision_plane_shadow_compare": _probe(
            "decision_plane_shadow_compare",
            DecisionPlaneShadowCompareCommand,
            run_decision_plane_shadow_compare,
        ),
        "citation_support_case": _probe(
            "citation_support_case",
            CitationSupportCaseCommand,
            run_citation_support_case,
        ),
        "context_budget_case": _probe(
            "context_budget_case",
            ContextBudgetCaseCommand,
            run_context_budget_case,
        ),
        "requirements_gap_case": _probe(
            "requirements_gap_case",
            RequirementsGapCaseCommand,
            run_requirements_gap_case,
        ),
        "task_route_case": _probe(
            "task_route_case", TaskRouteCaseCommand, run_task_route_case
        ),
        "action_safety_case": _probe(
            "action_safety_case",
            ActionSafetyCaseCommand,
            run_action_safety_case,
        ),
    }
    probes.update(pure_api_cli_probe_classes())
    return probes


__all__ = ["story_cli_probe_classes"]
