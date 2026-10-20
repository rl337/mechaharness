# User-story → CLI / `user_story` migration batches

| Surface | Value |
|---------|-------|
| Status | living checklist |
| Destination | `kind: user_story` scenario YAML (wraps product CLI verbs) |
| Already done | `fangore_insp_guidance_resume_idempotent`, `nubble_anthropic_cassette_infer`, `nubble_run_cost_events` |

## Goal

Convert every remaining acceptance story from legacy `kind: cli` script
YAML (and especially `probe:`) onto the persona-task harness:
`environment` → `graph` → `steps` → `complete` → `cleanup`.

Production CLI verbs stay as designed. Probes only until a product verb
exists for that claim.

## Counts

- Done (`user_story`): **49** (3 pilots + Wave 1 A–F + Wave 2 P1)
- Ready (product CLI verbs, no probe): **0**
- Blocked on probe → product verb: **124**

## Wave order

1. **Product batches A–F** (mechanical YAML + narrative tighten; no new verbs) — done.
2. **Probe batches P1–P10** (each wave may add a thin product verb, then migrate).
3. After each batch: regenerate `docs/guides/user-stories.md`, ratchet
   `fail_under` if coverage rose, keep `./run_checks.sh` green.

### Per-story checklist

1. Rewrite `narrative` as one persona walk (CLI host → graph → steps → verify).
2. Split if the walk cannot stay one task (see split review).
3. Convert scenario(s) to `kind: user_story`; set `story.json` `kind` accordingly.
4. Sync twins if present; update cross-refs that cited the old bag id.
5. Prefer product verbs in `steps[].do` — no `probe`.

## Product batches (A–F) — **done** (Wave 1)

### Batch A — Durable IoC product verbs

_start/answer/inspect/rebuild → user_story with graph.durable_ · **7** stories

- [x] `fangore_insp_driver_session_resume`
- [x] `fangore_insp_durable_graph_generator`
- [x] `fangore_insp_graph_guidance_yield`
- [x] `fangore_insp_guidance_controller_auth`
- [x] `fangore_insp_guidance_survive_restart`
- [x] `nubble_insp_guidance_cost_budget`
- [x] `taloneth_insp_scripted_driver_replay`

### Batch B — Recipe shape (instantiate/tile)

_instantiate_recipe / tile_recipe + binds/_ · **11** stories

- [x] `fangore_bounded_retry_recipe`
- [x] `fangore_environment_repair_recipe`
- [x] `fangore_graph_template_soft_points`
- [x] `fangore_insp_independent_review`
- [x] `fangore_insp_initialize_preflight`
- [x] `fangore_insp_produce_critique_refine`
- [x] `fangore_insp_template_incubation`
- [x] `fangore_node_components`
- [x] `fangore_recipe_namespace_tile`
- [x] `fangore_verify_repair_recipe`
- [x] `taloneth_insp_safety_eval_recipes`

### Batch C — Recipe plan lifecycle

_recipe_plan + plans/_ · **10** stories

- [x] `fangore_insp_evolution_ownership_split`
- [x] `fangore_insp_recipe_lineage_promote`
- [x] `fangore_insp_recipe_port_search`
- [x] `fangore_insp_recipe_version_pointer`
- [x] `fangore_insp_registry_only_compose`
- [x] `fangore_insp_soft_evolution_allowlist`
- [x] `fangore_recipe_as_tool`
- [x] `fangore_traversal_contract`
- [x] `taloneth_insp_recipe_evolution_loop`
- [x] `taloneth_insp_recipe_final_test_gate`

### Batch D — Execute harness / tool_loop

_run_recipe / tool_loop + environment.family_ · **5** stories

- [x] `fangore_backend_describe_recipe`
- [x] `fangore_conversational_tool_loop`
- [x] `fangore_harness_family_react`
- [x] `fangore_harness_run_recipe`
- [x] `fangore_harness_tool_loop_graph`

### Batch E — Diagnostics + judge

_judge_route / routing / parity / shadow / replay_ · **6** stories

- [x] `fangore_refund_verdict`
- [x] `nubble_insp_model_input_replay`
- [x] `nubble_insp_model_routing`
- [x] `nubble_model_affinity`
- [x] `taloneth_insp_run_parity`
- [x] `taloneth_shadow_decision_backends`

### Batch F — Infer leftovers

_infer + environment_ · **1** stories

- [x] `fangore_host_kit_event_tap`

## Probe batches (P1–P10) — verb then convert

Do not force `user_story` while the only driver is `probe:`. Add or reuse a
product verb first, then migrate the batch.

### Batch P10 — Misc probes

_Catch-all residuals_ · **5** stories

- [ ] `fangore_decision_surface_reject`
- [ ] `fangore_insp_decision_conflict_checkpoint`
- [ ] `nubble_insp_recipe_audit_dimensions`
- [ ] `nubble_insp_review_audit_reconstruct`
- [ ] `taloneth_insp_correction_spec_debt`

### Batch P1 — TDR crash windows — **done** (Wave 2)

_`transactional_resume` product verb_ · **6** stories

- [x] `fangore_tdr_crash_after_accept_before_record`
- [x] `fangore_tdr_crash_after_accept_recorded`
- [x] `fangore_tdr_crash_after_final_commit`
- [x] `fangore_tdr_crash_after_intent_before_call`
- [x] `fangore_tdr_crash_after_reduce_before_checkpoint`
- [x] `fangore_tdr_crash_before_intent`

### Batch P2 — JEV decision cases

_Promote citation/context/req/router probes onto decision_plane run_recipe or new verbs_ · **17** stories

- [ ] `fangore_jev_action_safety`
- [ ] `fangore_jev_citation_growth_mismatch`
- [ ] `fangore_jev_citation_matching_claim`
- [ ] `fangore_jev_citation_missing_source`
- [ ] `fangore_jev_citation_uncertain_support`
- [ ] `fangore_jev_context_budget_pack`
- [ ] `fangore_jev_context_exclude_injection`
- [ ] `fangore_jev_context_filter_stale_untrusted`
- [ ] `fangore_jev_context_missing_scores_fallback`
- [ ] `fangore_jev_req_review_approve_missing_crash_tests`
- [ ] `fangore_jev_req_review_covered_with_tests`
- [ ] `fangore_jev_req_review_gap_found`
- [ ] `fangore_jev_req_review_template_shape`
- [ ] `fangore_jev_task_route_complex_frontier`
- [ ] `fangore_jev_task_route_invalid`
- [ ] `fangore_jev_task_route_low_confidence`
- [ ] `fangore_jev_task_route_simple_local`

### Batch P3 — Decision plane core

_run_recipe decision_plane / policy expects_ · **6** stories

- [ ] `fangore_decision_plane_model_policy`
- [ ] `fangore_decision_plane_policy`
- [ ] `fangore_decision_plane_projection`
- [ ] `fangore_decision_plane_recipe`
- [ ] `fangore_decision_plane_shadow`
- [ ] `fangore_decision_plane_telemetry`

### Batch P4 — Lifecycle extensions

_Product lifecycle verb or host extension CLI_ · **5** stories

- [ ] `fangore_insp_lifecycle_block`
- [ ] `fangore_insp_lifecycle_graph_observe`
- [ ] `fangore_insp_lifecycle_observe`
- [ ] `fangore_insp_lifecycle_replace`
- [ ] `fangore_insp_lifecycle_rewrite`

### Batch P5 — Access / authority

_Grants, epochs, envelopes — product verbs TBD_ · **17** stories

- [ ] `fangore_capability_envelope_narrow`
- [ ] `fangore_compound_grants`
- [ ] `fangore_config_access_policy`
- [ ] `fangore_human_review_pending`
- [ ] `fangore_insp_alert_escalation_rules`
- [ ] `fangore_insp_approval_interrupt`
- [ ] `fangore_insp_auth_epoch_resume`
- [ ] `fangore_insp_authority_gate`
- [ ] `fangore_insp_cross_task_isolation`
- [ ] `fangore_insp_denial_equivalence`
- [ ] `fangore_insp_effect_revalidation`
- [ ] `fangore_insp_execution_token`
- [ ] `fangore_insp_isolation_io`
- [ ] `fangore_insp_tool_effect_classes`
- [ ] `fangore_insp_tool_result_freshness`
- [ ] `nubble_insp_workspace_isolation`
- [ ] `nubble_lane_load_hint`

### Batch P6 — Context management

_Context assembly verbs TBD_ · **11** stories

- [ ] `fangore_context_compiler_deficit`
- [ ] `fangore_context_observation_chain`
- [ ] `fangore_derived_memory`
- [ ] `fangore_insp_anchor_evidence`
- [ ] `fangore_insp_context_compaction`
- [ ] `fangore_insp_context_layers`
- [ ] `fangore_insp_context_provider`
- [ ] `fangore_insp_instruction_gotchas`
- [ ] `fangore_insp_instruction_scope`
- [ ] `nubble_repo_topology`
- [ ] `taloneth_cache_layout_experiment`

### Batch P7 — Eval / research

_Taloneth eval probes → product verbs TBD_ · **28** stories

- [ ] `fangore_insp_failure_attribution`
- [ ] `nubble_insp_efficiency_scorecard`
- [ ] `nubble_insp_trace_envelope`
- [ ] `nubble_insp_trace_reconciliation`
- [ ] `taloneth_atk_research_reject`
- [ ] `taloneth_decision_plane_shadow_compare`
- [ ] `taloneth_fixture_judge_batch`
- [ ] `taloneth_insp_component_ablation`
- [ ] `taloneth_insp_cross_harness_failure`
- [ ] `taloneth_insp_eval_claims`
- [ ] `taloneth_insp_eval_matrix`
- [ ] `taloneth_insp_evaluation_outcome`
- [ ] `taloneth_insp_evaluator_compose`
- [ ] `taloneth_insp_experiment_dimensions`
- [ ] `taloneth_insp_experiment_lineage`
- [ ] `taloneth_insp_exposure_discriminative`
- [ ] `taloneth_insp_gated_objective`
- [ ] `taloneth_insp_harness_fingerprint`
- [ ] `taloneth_insp_harness_health`
- [ ] `taloneth_insp_harness_hypothesis`
- [ ] `taloneth_insp_learning_export`
- [ ] `taloneth_insp_objective_policy`
- [ ] `taloneth_insp_rule_promotion`
- [ ] `taloneth_insp_scaffolding_retire`
- [ ] `taloneth_insp_trial_reliability`
- [ ] `taloneth_offline_decision_export`
- [ ] `taloneth_policy_replay`
- [ ] `taloneth_validator_qualification`

### Batch P8 — Graph executor / budgets

_Executor/budget/resume probes → durable/run_recipe_ · **18** stories

- [ ] `fangore_bounded_repair_loop`
- [ ] `fangore_convergence_ceiling`
- [ ] `fangore_graph_executor`
- [ ] `fangore_graph_linkage_preflight`
- [ ] `fangore_host_kit_submit_once`
- [ ] `fangore_insp_budget_subgraph_rollup`
- [ ] `fangore_insp_durable_resume`
- [ ] `fangore_insp_dynamic_subgraph`
- [ ] `fangore_insp_graph_budget`
- [ ] `fangore_insp_graph_transitions`
- [ ] `fangore_insp_linkage_preflight`
- [ ] `fangore_insp_soft_vs_hard`
- [ ] `fangore_insp_targeted_rollback`
- [ ] `fangore_insp_wake_reresolve`
- [ ] `fangore_local_plan_resume`
- [ ] `nubble_graph_event_correlators`
- [ ] `nubble_insp_environment_linkage`
- [ ] `nubble_insp_rollout_graph`

### Batch P9 — Pure API / policy helpers

_fan_in, wip, sparse advisor — product diagnostic verbs or stay unit_ · **17** stories

- [ ] `fangore_completer_flavors`
- [ ] `fangore_insp_exit_clean_state`
- [ ] `fangore_insp_fan_in_policy`
- [ ] `fangore_insp_handoff_record`
- [ ] `fangore_insp_inference_capture_preflight`
- [ ] `fangore_insp_loop_health`
- [ ] `fangore_insp_operation_compensation`
- [ ] `fangore_insp_risk_autonomy`
- [ ] `fangore_insp_sparse_advisor`
- [ ] `fangore_insp_state_governance`
- [ ] `fangore_insp_stop_contract`
- [ ] `fangore_insp_verification_gate`
- [ ] `fangore_insp_wip_backpressure`
- [ ] `nubble_insp_coordination_cost`
- [ ] `nubble_insp_environment_delta`
- [ ] `nubble_insp_resume_cost`
- [ ] `nubble_topology_efficiency`

## Related

- [`.cursor/skills/user-stories/SKILL.md`](../../.cursor/skills/user-stories/SKILL.md)
- [`docs/reference/cli-universe.md`](../reference/cli-universe.md)
- `tests/stories/scenarios/user_story_scenario.py`

