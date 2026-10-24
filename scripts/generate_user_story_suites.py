#!/usr/bin/env python3
"""Author static suite.json files from exclusive story→suite membership.

Usage:
  python scripts/generate_user_story_suites.py          # write suites
  python scripts/generate_user_story_suites.py --check  # exit 1 if drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.stories.catalog import iter_story_cases  # noqa: E402
from tests.stories.suite_catalog import static_suites_root  # noqa: E402

# Suite catalog metadata + exclusive prefix/exact membership.
# Each static story id maps to exactly one suite.
SUITE_META: dict[str, dict[str, str]] = {
    "fangore_durable_ioc": {
        "title": "Durable IoC, guidance yield, and local plan resume",
        "persona": "fangore",
    },
    "fangore_guided_coding": {
        "title": "Guided coding recipe and instruction todo plan",
        "persona": "fangore",
    },
    "fangore_decision_plane": {
        "title": "Decision plane policy, projection, and audited infer",
        "persona": "fangore",
    },
    "fangore_access_authority": {
        "title": "Grants, capability envelopes, and authority gates",
        "persona": "fangore",
    },
    "fangore_job_lanes": {
        "title": "Job lane exposure, handoff, and deny rules",
        "persona": "fangore",
    },
    "fangore_graph_executor": {
        "title": "Graph executor, soft points, traversal, and budgets",
        "persona": "fangore",
    },
    "fangore_recipes_tiling": {
        "title": "Agentic Recipe tiling and repair loops",
        "persona": "fangore",
    },
    "fangore_context_memory": {
        "title": "Context layers, compaction, and derived memory",
        "persona": "fangore",
    },
    "fangore_host_kit": {
        "title": "Host kit, completer flavors, and harness families",
        "persona": "fangore",
    },
    "fangore_tdr_crash": {
        "title": "Transactionally durable crash recovery",
        "persona": "fangore",
    },
    "fangore_jev": {
        "title": "Judge evaluation vocabulary scenarios",
        "persona": "fangore",
    },
    "fangore_lifecycle_ops": {
        "title": "Lifecycle extensions, wake, WIP, and tool effects",
        "persona": "fangore",
    },
    "fangore_recipe_registry": {
        "title": "Recipe registry lineage, ports, and soft evolution",
        "persona": "fangore",
    },
    "nubble_observability": {
        "title": "Cost, trace, and audit observability",
        "persona": "nubble",
    },
    "nubble_routing_topology": {
        "title": "Model routing, lanes, and environment topology",
        "persona": "nubble",
    },
    "taloneth_decision_eval": {
        "title": "Offline decision eval, shadow, and exports",
        "persona": "taloneth",
    },
    "taloneth_harness_research": {
        "title": "Harness research, ablation, and promotion gates",
        "persona": "taloneth",
    },
    "calc_cli": {
        "title": "Grow a CLI math expression calculator",
        "persona": "fangore",
    },
    "counter_pkg": {
        "title": "Grow a Counter package with tests and CLI",
        "persona": "fangore",
    },
    "delegate_pkg": {
        "title": "Delegate coding arcs on a shared Widget package",
        "persona": "fangore",
    },
}

# Sequential / ordered suites: stages keep authored order; not regenerated as parallel.
SEQUENTIAL_SUITE_IDS = frozenset({"calc_cli", "counter_pkg", "delegate_pkg"})

# Explicit ordered stage list for sequential suites (story, scenario).
SEQUENTIAL_STAGE_ORDER: dict[str, list[tuple[str, str]]] = {
    "calc_cli": [
        ("fangore_calc_parse_number", "bootstrap"),
        ("fangore_calc_add_sub", "add_sub"),
        ("fangore_calc_mul_div", "mul_div"),
        ("fangore_calc_exponent", "exponent"),
        ("fangore_calc_grouping", "grouping"),
        ("fangore_calc_functions", "functions"),
    ],
    "counter_pkg": [
        ("fangore_counter_bootstrap", "bootstrap"),
        ("fangore_counter_mutate", "mutate"),
        ("fangore_counter_persist", "persist"),
        ("fangore_counter_cli", "cli"),
    ],
    "delegate_pkg": [
        ("fangore_delegate_list_bootstrap", "list_bootstrap"),
        ("fangore_delegate_guidance_thorough", "guidance_thorough"),
        ("fangore_delegate_red_green", "red_green"),
        ("fangore_delegate_refactor", "refactor"),
    ],
}

# Exact story id → suite (checked before prefixes).
EXACT: dict[str, str] = {
    # durable IoC
    "fangore_local_plan_resume": "fangore_durable_ioc",
    "fangore_insp_durable_graph_generator": "fangore_durable_ioc",
    "fangore_insp_durable_resume": "fangore_durable_ioc",
    "fangore_insp_guidance_controller_auth": "fangore_durable_ioc",
    "fangore_insp_guidance_resume_idempotent": "fangore_durable_ioc",
    "fangore_insp_guidance_survive_restart": "fangore_durable_ioc",
    "fangore_insp_graph_guidance_yield": "fangore_durable_ioc",
    "fangore_insp_driver_session_resume": "fangore_durable_ioc",
    "fangore_insp_sparse_advisor": "fangore_durable_ioc",
    "fangore_insp_approval_interrupt": "fangore_durable_ioc",
    # guided coding
    "fangore_guided_coding_recipe": "fangore_guided_coding",
    "fangore_instruction_todo_plan": "fangore_guided_coding",
    "fangore_insp_instruction_gotchas": "fangore_guided_coding",
    "fangore_insp_instruction_scope": "fangore_guided_coding",
    "fangore_coding_git_inspect": "fangore_guided_coding",
    "fangore_coding_git_open_pr": "fangore_guided_coding",
    "fangore_coding_ci_diagnose": "fangore_guided_coding",
    "fangore_coding_ci_repair": "fangore_guided_coding",
    "fangore_coding_write_guard": "fangore_guided_coding",
    # decision plane
    "fangore_audited_infer_accept": "fangore_decision_plane",
    "fangore_refund_verdict": "fangore_decision_plane",
    "fangore_decision_surface_reject": "fangore_decision_plane",
    "fangore_insp_decision_conflict_checkpoint": "fangore_decision_plane",
    "fangore_insp_anchor_evidence": "fangore_decision_plane",
    # access / authority
    "fangore_capability_envelope_narrow": "fangore_access_authority",
    "fangore_compound_grants": "fangore_access_authority",
    "fangore_human_review_pending": "fangore_access_authority",
    "fangore_insp_auth_epoch_resume": "fangore_access_authority",
    "fangore_insp_authority_gate": "fangore_access_authority",
    "fangore_insp_denial_equivalence": "fangore_access_authority",
    "fangore_insp_execution_token": "fangore_access_authority",
    "fangore_insp_risk_autonomy": "fangore_access_authority",
    "fangore_insp_soft_vs_hard": "fangore_access_authority",
    "fangore_insp_cross_task_isolation": "fangore_access_authority",
    "fangore_insp_state_governance": "fangore_access_authority",
    "fangore_insp_evolution_ownership_split": "fangore_access_authority",
    "fangore_insp_isolation_io": "fangore_access_authority",
    # graph executor extras
    "fangore_node_components": "fangore_graph_executor",
    "fangore_traversal_contract": "fangore_graph_executor",
    "fangore_convergence_ceiling": "fangore_graph_executor",
    "fangore_insp_budget_subgraph_rollup": "fangore_graph_executor",
    "fangore_insp_linkage_preflight": "fangore_graph_executor",
    "fangore_insp_dynamic_subgraph": "fangore_graph_executor",
    "fangore_insp_loop_health": "fangore_graph_executor",
    "fangore_insp_exit_clean_state": "fangore_graph_executor",
    "fangore_insp_failure_attribution": "fangore_graph_executor",
    "fangore_insp_targeted_rollback": "fangore_graph_executor",
    "fangore_insp_verification_gate": "fangore_graph_executor",
    "fangore_insp_inference_capture_preflight": "fangore_graph_executor",
    "fangore_insp_graph_budget": "fangore_graph_executor",
    "fangore_insp_graph_transitions": "fangore_graph_executor",
    # recipes / tiling
    "fangore_verify_repair_recipe": "fangore_recipes_tiling",
    "fangore_bounded_repair_loop": "fangore_recipes_tiling",
    "fangore_bounded_retry_recipe": "fangore_recipes_tiling",
    "fangore_conversational_tool_loop": "fangore_recipes_tiling",
    "fangore_environment_repair_recipe": "fangore_recipes_tiling",
    "fangore_recipe_as_tool": "fangore_recipes_tiling",
    "fangore_recipe_namespace_tile": "fangore_recipes_tiling",
    "fangore_insp_produce_critique_refine": "fangore_recipes_tiling",
    "fangore_insp_independent_review": "fangore_recipes_tiling",
    "fangore_insp_initialize_preflight": "fangore_recipes_tiling",
    "fangore_insp_fan_in_policy": "fangore_recipes_tiling",
    "fangore_insp_stop_contract": "fangore_recipes_tiling",
    # context
    "fangore_derived_memory": "fangore_context_memory",
    # host kit
    "fangore_completer_flavors": "fangore_host_kit",
    "fangore_config_access_policy": "fangore_host_kit",
    "fangore_backend_describe_recipe": "fangore_host_kit",
    # recipe registry
    "fangore_insp_recipe_lineage_promote": "fangore_recipe_registry",
    "fangore_insp_recipe_port_search": "fangore_recipe_registry",
    "fangore_insp_recipe_version_pointer": "fangore_recipe_registry",
    "fangore_insp_registry_only_compose": "fangore_recipe_registry",
    "fangore_insp_soft_evolution_allowlist": "fangore_recipe_registry",
    "fangore_insp_template_incubation": "fangore_recipe_registry",
    # lifecycle
    "fangore_insp_wake_reresolve": "fangore_lifecycle_ops",
    "fangore_insp_wip_backpressure": "fangore_lifecycle_ops",
    "fangore_insp_handoff_record": "fangore_lifecycle_ops",
    "fangore_insp_operation_compensation": "fangore_lifecycle_ops",
    "fangore_insp_effect_revalidation": "fangore_lifecycle_ops",
    "fangore_insp_tool_effect_classes": "fangore_lifecycle_ops",
    "fangore_insp_tool_result_freshness": "fangore_lifecycle_ops",
    "fangore_insp_alert_escalation_rules": "fangore_lifecycle_ops",
    # nubble observability extras
    "nubble_run_cost_events": "nubble_observability",
    "nubble_graph_event_correlators": "nubble_observability",
    "nubble_anthropic_cassette_infer": "nubble_observability",
    "nubble_insp_model_input_replay": "nubble_observability",
    # nubble routing
    "nubble_model_affinity": "nubble_routing_topology",
    "nubble_lane_load_hint": "nubble_routing_topology",
    "nubble_repo_topology": "nubble_routing_topology",
    "nubble_topology_efficiency": "nubble_routing_topology",
    # taloneth decision
    "taloneth_fixture_judge_batch": "taloneth_decision_eval",
    "taloneth_policy_replay": "taloneth_decision_eval",
    "taloneth_shadow_decision_backends": "taloneth_decision_eval",
    "taloneth_decision_plane_shadow_compare": "taloneth_decision_eval",
    "taloneth_offline_decision_export": "taloneth_decision_eval",
    "taloneth_validator_qualification": "taloneth_decision_eval",
    "taloneth_atk_research_reject": "taloneth_harness_research",
    "taloneth_cache_layout_experiment": "taloneth_harness_research",
    # sequential calc_cli arc
    "fangore_calc_parse_number": "calc_cli",
    "fangore_calc_add_sub": "calc_cli",
    "fangore_calc_mul_div": "calc_cli",
    "fangore_calc_exponent": "calc_cli",
    "fangore_calc_grouping": "calc_cli",
    "fangore_calc_functions": "calc_cli",
    # sequential counter_pkg arc (multi-file + pytest)
    "fangore_counter_bootstrap": "counter_pkg",
    "fangore_counter_mutate": "counter_pkg",
    "fangore_counter_persist": "counter_pkg",
    "fangore_counter_cli": "counter_pkg",
    # sequential delegate_pkg arc (list / guidance / red-green / refactor)
    "fangore_delegate_list_bootstrap": "delegate_pkg",
    "fangore_delegate_guidance_thorough": "delegate_pkg",
    "fangore_delegate_red_green": "delegate_pkg",
    "fangore_delegate_refactor": "delegate_pkg",
}

PREFIXES: list[tuple[str, str]] = [
    ("fangore_decision_plane_", "fangore_decision_plane"),
    ("fangore_job_lane_", "fangore_job_lanes"),
    ("fangore_graph_", "fangore_graph_executor"),
    ("fangore_context_", "fangore_context_memory"),
    ("fangore_insp_context_", "fangore_context_memory"),
    ("fangore_host_kit_", "fangore_host_kit"),
    ("fangore_harness_", "fangore_host_kit"),
    ("fangore_tdr_crash_", "fangore_tdr_crash"),
    ("fangore_jev_", "fangore_jev"),
    ("fangore_insp_lifecycle_", "fangore_lifecycle_ops"),
    ("nubble_insp_trace_", "nubble_observability"),
    ("nubble_insp_resume_cost", "nubble_observability"),
    ("nubble_insp_guidance_cost", "nubble_observability"),
    ("nubble_insp_coordination_cost", "nubble_observability"),
    ("nubble_insp_efficiency_scorecard", "nubble_observability"),
    ("nubble_insp_recipe_audit", "nubble_observability"),
    ("nubble_insp_review_audit", "nubble_observability"),
    ("nubble_insp_model_routing", "nubble_routing_topology"),
    ("nubble_insp_environment_", "nubble_routing_topology"),
    ("nubble_insp_workspace_isolation", "nubble_routing_topology"),
    ("nubble_insp_rollout_graph", "nubble_routing_topology"),
    ("taloneth_insp_", "taloneth_harness_research"),
]


def assign_suite(story_id: str) -> str:
    if story_id in EXACT:
        return EXACT[story_id]
    for prefix, suite_id in PREFIXES:
        if story_id.startswith(prefix):
            return suite_id
    raise KeyError(f"no suite membership for story {story_id!r}")


def collect_static_stages() -> dict[str, list[dict[str, str]]]:
    by_suite: dict[str, list[dict[str, str]]] = {sid: [] for sid in SUITE_META}
    seen_stories: set[str] = set()
    for case in iter_story_cases():
        if "static/fixture" not in case.root.as_posix():
            continue
        if case.scenario_relpath is None:
            continue
        stem = Path(case.scenario_relpath).stem
        suite_id = assign_suite(case.story_id)
        by_suite[suite_id].append({"story": case.story_id, "scenario": stem})
        seen_stories.add(case.story_id)
    for suite_id, stages in by_suite.items():
        if suite_id in SEQUENTIAL_SUITE_IDS:
            order = {
                (story, scenario): idx
                for idx, (story, scenario) in enumerate(
                    SEQUENTIAL_STAGE_ORDER.get(suite_id, [])
                )
            }
            stages.sort(
                key=lambda s: order.get((s["story"], s["scenario"]), 10_000)
            )
        else:
            stages.sort(key=lambda s: (s["story"], s["scenario"]))
    # Ensure every static story directory was assigned.
    stories_dir = ROOT / "tests/fixtures/models/static/fixture/v1/stories"
    for path in sorted(p for p in stories_dir.iterdir() if p.is_dir()):
        if path.name not in seen_stories:
            raise SystemExit(f"static story {path.name!r} has no scenarios")
    return by_suite


def render_suite(suite_id: str, stages: list[dict[str, str]]) -> dict:
    meta = SUITE_META[suite_id]
    if suite_id in SEQUENTIAL_SUITE_IDS:
        return {
            "id": suite_id,
            "title": meta["title"],
            "persona": meta["persona"],
            "execution": {"mode": "sequential", "ordered": True},
            "vars": {},
            "setup": ["ensure_workspace"],
            "cleanup": [],
            "workspace": "temp",
            "stages": stages,
        }
    return {
        "id": suite_id,
        "title": meta["title"],
        "persona": meta["persona"],
        "execution": {"mode": "parallel", "ordered": False},
        "vars": {},
        "setup": [],
        "cleanup": [],
        "stages": stages,
    }


def write_suites() -> list[Path]:
    by_suite = collect_static_stages()
    root = static_suites_root()
    written: list[Path] = []
    for suite_id, stages in sorted(by_suite.items()):
        if not stages:
            raise SystemExit(f"suite {suite_id!r} has zero stages")
        if suite_id in SEQUENTIAL_SUITE_IDS:
            expected_keys = [
                {"story": s, "scenario": sc}
                for s, sc in SEQUENTIAL_STAGE_ORDER[suite_id]
            ]
            if stages != expected_keys:
                raise SystemExit(
                    f"suite {suite_id!r} stages {stages} != ordered {expected_keys}"
                )
        suite_dir = root / suite_id
        suite_dir.mkdir(parents=True, exist_ok=True)
        path = suite_dir / "suite.json"
        payload = render_suite(suite_id, stages)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    # Remove stale suite dirs not in catalog (keep sequential source trees).
    if root.is_dir():
        for child in list(root.iterdir()):
            if child.is_dir() and child.name not in SUITE_META:
                stale = child / "suite.json"
                if stale.is_file():
                    stale.unlink()
                try:
                    child.rmdir()
                except OSError:
                    pass
    return written


def check_suites() -> list[str]:
    errors: list[str] = []
    by_suite = collect_static_stages()
    root = static_suites_root()
    for suite_id, stages in sorted(by_suite.items()):
        path = root / suite_id / "suite.json"
        expected = render_suite(suite_id, stages)
        if not path.is_file():
            errors.append(f"missing {path}")
            continue
        actual = json.loads(path.read_text(encoding="utf-8"))
        if actual != expected:
            errors.append(f"drift in {path}")
    if root.is_dir():
        for child in sorted(p for p in root.iterdir() if p.is_dir()):
            if child.name not in SUITE_META:
                errors.append(f"unexpected suite dir {child}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if suite.json files drift from membership",
    )
    args = parser.parse_args(argv)
    if args.check:
        errors = check_suites()
        if errors:
            print("suite membership check failed:", file=sys.stderr)
            for err in errors:
                print(f"  {err}", file=sys.stderr)
            return 1
        print(f"ok: suites match membership ({len(SUITE_META)} suites)")
        return 0
    written = write_suites()
    print(f"wrote {len(written)} suite.json files under {static_suites_root()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
