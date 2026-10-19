"""Map-multibind contributions for story acceptance probes."""

from __future__ import annotations

from mechaharness.cli_verb import CliVerb, make_probe_verb
from tests.stories.cli_probes.acceptance_verbs import (
    CheckCompleterFlavorsCommand,
    CheckInferenceCaptureCommand,
    HostKitSubmitOnceCommand,
    run_check_completer_flavors,
    run_check_inference_capture,
    run_host_kit_submit_once,
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


def story_cli_verb_classes() -> dict[str, type[CliVerb]]:
    """Acceptance probes merged into story Config via ``cli_verb_classes()``."""
    return {
        "check_completer_flavors": make_probe_verb(
            "check_completer_flavors",
            CheckCompleterFlavorsCommand,
            run_check_completer_flavors,
        ),
        "check_inference_capture": make_probe_verb(
            "check_inference_capture",
            CheckInferenceCaptureCommand,
            run_check_inference_capture,
        ),
        "host_kit_submit_once": make_probe_verb(
            "host_kit_submit_once",
            HostKitSubmitOnceCommand,
            run_host_kit_submit_once,
        ),
        "topology_efficiency": make_probe_verb(
            "topology_efficiency",
            TopologyEfficiencyCommand,
            run_topology_efficiency,
        ),
        "validator_qualification": make_probe_verb(
            "validator_qualification",
            ValidatorQualificationCommand,
            run_validator_qualification,
        ),
        "bounded_repair_loop": make_probe_verb(
            "bounded_repair_loop",
            BoundedRepairLoopCommand,
            run_bounded_repair_loop,
        ),
        "graph_executor_run": make_probe_verb(
            "graph_executor_run",
            GraphExecutorRunCommand,
            run_graph_executor_run,
        ),
        "graph_event_correlators": make_probe_verb(
            "graph_event_correlators",
            GraphEventCorrelatorsCommand,
            run_graph_event_correlators,
        ),
        "graph_linkage_preflight": make_probe_verb(
            "graph_linkage_preflight",
            GraphLinkagePreflightCommand,
            run_graph_linkage_preflight,
        ),
        "graph_transition_inspect": make_probe_verb(
            "graph_transition_inspect",
            GraphTransitionInspectCommand,
            run_graph_transition_inspect,
        ),
        "targeted_rollback_select": make_probe_verb(
            "targeted_rollback_select",
            TargetedRollbackSelectCommand,
            run_targeted_rollback_select,
        ),
        "rollout_graph_build": make_probe_verb(
            "rollout_graph_build",
            RolloutGraphBuildCommand,
            run_rollout_graph_build,
        ),
        "convergence_ceiling": make_probe_verb(
            "convergence_ceiling",
            ConvergenceCeilingCommand,
            run_convergence_ceiling,
        ),
        "local_plan_resume": make_probe_verb(
            "local_plan_resume",
            LocalPlanResumeCommand,
            run_local_plan_resume,
        ),
        "dynamic_subgraph_nest": make_probe_verb(
            "dynamic_subgraph_nest",
            DynamicSubgraphNestCommand,
            run_dynamic_subgraph_nest,
        ),
        "checkpoint_fingerprint_refuse": make_probe_verb(
            "checkpoint_fingerprint_refuse",
            CheckpointFingerprintRefuseCommand,
            run_checkpoint_fingerprint_refuse,
        ),
        "environment_linkage_fail": make_probe_verb(
            "environment_linkage_fail",
            EnvironmentLinkageFailCommand,
            run_environment_linkage_fail,
        ),
        "wake_reresolve_resume": make_probe_verb(
            "wake_reresolve_resume",
            WakeReresolveResumeCommand,
            run_wake_reresolve_resume,
        ),
        "graph_budget_limits": make_probe_verb(
            "graph_budget_limits",
            GraphBudgetLimitsCommand,
            run_graph_budget_limits,
        ),
        "graph_budget_subgraph_rollup": make_probe_verb(
            "graph_budget_subgraph_rollup",
            GraphBudgetSubgraphRollupCommand,
            run_graph_budget_subgraph_rollup,
        ),
        "transactional_durable_resume": make_probe_verb(
            "transactional_durable_resume",
            TransactionalDurableResumeCommand,
            run_transactional_durable_resume,
        ),
        "decision_conflict_neighbor_revisit": make_probe_verb(
            "decision_conflict_neighbor_revisit",
            DecisionConflictNeighborRevisitCommand,
            run_decision_conflict_neighbor_revisit,
        ),
    }
