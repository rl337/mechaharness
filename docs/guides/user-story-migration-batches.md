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

- Done (`user_story`): regenerate via `scripts/generate_user_stories_md.py`
- Wave 3 (P2–P4 rewrite): case bags removed; see
  [instrumentation migration](./user-story-instrumentation-migration.md)
- **Wave 4+:** remaining work is **recipe-first groups G0–G7**, not thin-verb
  then YAML wrap — see
  [recipe expansion](./user-story-recipe-expansion.md)

## Wave order

1. **Product batches A–F** (mechanical YAML + narrative tighten; no new verbs) — done.
2. **Probe batches P1–P4** — done (P3 demotions retracted; restore in G0).
3. **Instrumentation (Wave 3)** — case-bag verbs removed; gold =
   soft-bind + execute + cassette/live
   ([plan](./user-story-instrumentation-migration.md)).
4. **Recipe expansion (Wave 4+)** — invent/extend Agentic Recipes + runners,
   then migrate probes / promote shape-only stories
   ([groups](./user-story-recipe-expansion.md)). P5–P10 checklists below are
   **historical inventory**; work them via G0–G7, not as probe→thin-verb waves.
5. After each batch: regenerate `docs/guides/user-stories.md`, ratchet
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

### Batch B — Recipe shape (instantiate/tile) — **done interim** · promote via **G1**

_instantiate_recipe / tile_recipe + binds/_ · **11** stories.
Many claims are outcome walks — promote to execute when runners land
([G1](./user-story-recipe-expansion.md)).

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

### Batch C — Recipe plan lifecycle — **done interim** · see **G6**

_recipe_plan + plans/_ · **10** stories.
Keep for registry lifecycle claims; promote to execute when the story is “run
the evolved recipe” ([G6](./user-story-recipe-expansion.md)).

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

## Probe batches (P1–P10) — historical inventory

P1–P4 are done (reopen P3 demotions via G0). For P5–P10, do **not** add thin
`*_case` verbs then YAML-wrap. Invent/extend the Agentic Recipe, then migrate
([recipe expansion](./user-story-recipe-expansion.md)).

### Batch P10 — Misc probes → distribute across G0–G7

_Catch-all residuals — assign per claim when pulled_ · **5** stories

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

### Batch P2 — JEV decision cases — **done** (Wave 2) · **Wave 3 done**

_`judge` / `context_pack` / `instantiate_recipe` — see
[instrumentation migration](./user-story-instrumentation-migration.md)_ ·
**17** stories

- [x] `fangore_jev_action_safety`
- [x] `fangore_jev_citation_growth_mismatch`
- [x] `fangore_jev_citation_matching_claim`
- [x] `fangore_jev_citation_missing_source`
- [x] `fangore_jev_citation_uncertain_support`
- [x] `fangore_jev_context_budget_pack`
- [x] `fangore_jev_context_exclude_injection`
- [x] `fangore_jev_context_filter_stale_untrusted`
- [x] `fangore_jev_context_missing_scores_fallback`
- [x] `fangore_jev_req_review_approve_missing_crash_tests`
- [x] `fangore_jev_req_review_covered_with_tests`
- [x] `fangore_jev_req_review_gap_found`
- [x] `fangore_jev_req_review_template_shape`
- [x] `fangore_jev_task_route_complex_frontier`
- [x] `fangore_jev_task_route_invalid`
- [x] `fangore_jev_task_route_low_confidence`
- [x] `fangore_jev_task_route_simple_local`

### Batch P3 — Decision plane core — **done** (G0 execute)

_`run_recipe` + `DecisionPlaneRecipeAdapter` / `decision_plane_runner`
([recipe expansion G0](./user-story-recipe-expansion.md))._

- [x] `fangore_decision_plane_model_policy`
- [x] `fangore_decision_plane_policy`
- [x] `fangore_decision_plane_projection`
- [x] `fangore_decision_plane_recipe`
- [x] `fangore_decision_plane_shadow`
- [x] `fangore_decision_plane_telemetry`

### Batch P4 — Lifecycle extensions — **done** (Wave 2) · **Wave 3 done**

_`tool_lifecycle` + host-bound extensions — see
[instrumentation migration](./user-story-instrumentation-migration.md)_ ·
**5** stories

- [x] `fangore_insp_lifecycle_block`
- [x] `fangore_insp_lifecycle_graph_observe`
- [x] `fangore_insp_lifecycle_observe`
- [x] `fangore_insp_lifecycle_replace`
- [x] `fangore_insp_lifecycle_rewrite`

### Batch P5 — Access / authority → **G3**

_Historical list. Work via [G3](./user-story-recipe-expansion.md)
(authority gates on product graphs), not probe wrappers._ · **17** stories

- [x] `fangore_capability_envelope_narrow`
- [x] `fangore_compound_grants`
- [x] `fangore_config_access_policy`
- [x] `fangore_human_review_pending`
- [ ] `fangore_insp_alert_escalation_rules`
- [x] `fangore_insp_approval_interrupt`
- [x] `fangore_insp_auth_epoch_resume`
- [x] `fangore_insp_authority_gate`
- [ ] `fangore_insp_cross_task_isolation`
- [ ] `fangore_insp_denial_equivalence`
- [ ] `fangore_insp_effect_revalidation`
- [ ] `fangore_insp_execution_token`
- [ ] `fangore_insp_isolation_io`
- [ ] `fangore_insp_tool_effect_classes`
- [ ] `fangore_insp_tool_result_freshness`
- [ ] `nubble_insp_workspace_isolation`
- [ ] `nubble_lane_load_hint`

### Batch P6 — Context management → **G2**

_Historical list. Extend `context_pack` / `ContextProvider`
([G2](./user-story-recipe-expansion.md))._ · **11** stories

- [x] `fangore_context_compiler_deficit`
- [x] `fangore_context_observation_chain`
- [x] `fangore_derived_memory`
- [x] `fangore_insp_anchor_evidence`
- [x] `fangore_insp_context_compaction`
- [x] `fangore_insp_context_layers`
- [x] `fangore_insp_context_provider`
- [x] `fangore_insp_instruction_gotchas`
- [x] `fangore_insp_instruction_scope`
- [x] `nubble_repo_topology`
- [x] `taloneth_cache_layout_experiment`

### Batch P7 — Eval / research → **G5**

_Historical list. Prefer eval recipes / export graphs
([G5](./user-story-recipe-expansion.md))._ · **28** stories

- [x] `fangore_insp_failure_attribution`
- [x] `nubble_insp_efficiency_scorecard`
- [x] `nubble_insp_trace_envelope`
- [x] `nubble_insp_trace_reconciliation`
- [x] `taloneth_atk_research_reject`
- [x] `taloneth_decision_plane_shadow_compare`
- [x] `taloneth_fixture_judge_batch`
- [x] `taloneth_insp_component_ablation`
- [x] `taloneth_insp_cross_harness_failure`
- [x] `taloneth_insp_eval_claims`
- [x] `taloneth_insp_eval_matrix`
- [x] `taloneth_insp_evaluation_outcome`
- [x] `taloneth_insp_evaluator_compose`
- [x] `taloneth_insp_experiment_dimensions`
- [x] `taloneth_insp_experiment_lineage`
- [x] `taloneth_insp_exposure_discriminative`
- [x] `taloneth_insp_gated_objective`
- [x] `taloneth_insp_harness_fingerprint`
- [x] `taloneth_insp_harness_health`
- [x] `taloneth_insp_harness_hypothesis`
- [x] `taloneth_insp_learning_export`
- [x] `taloneth_insp_objective_policy`
- [x] `taloneth_insp_rule_promotion`
- [x] `taloneth_insp_scaffolding_retire`
- [x] `taloneth_insp_trial_reliability`
- [x] `taloneth_offline_decision_export`
- [x] `taloneth_policy_replay`
- [x] `taloneth_validator_qualification`

### Batch P8 — Graph executor / budgets → **G4** (+ some **G1**)

_Historical list. Durable/budget execute
([G4](./user-story-recipe-expansion.md));
`fangore_bounded_repair_loop` → verify_repair in G1._ · **18** stories

- [x] `fangore_bounded_repair_loop`
- [ ] `fangore_convergence_ceiling`
- [ ] `fangore_graph_executor`
- [ ] `fangore_graph_linkage_preflight`
- [ ] `fangore_host_kit_submit_once`
- [x] `fangore_insp_budget_subgraph_rollup`
- [ ] `fangore_insp_durable_resume`
- [ ] `fangore_insp_dynamic_subgraph`
- [x] `fangore_insp_graph_budget`
- [ ] `fangore_insp_graph_transitions`
- [ ] `fangore_insp_linkage_preflight`
- [ ] `fangore_insp_soft_vs_hard`
- [ ] `fangore_insp_targeted_rollback`
- [ ] `fangore_insp_wake_reresolve`
- [ ] `fangore_local_plan_resume`
- [ ] `nubble_graph_event_correlators`
- [ ] `nubble_insp_environment_linkage`
- [ ] `nubble_insp_rollout_graph`

### Batch P9 — Pure API / policy helpers → **G7** / selective recipes

_Historical list. Thin diagnostic verbs ok when not subgraph control
([G7](./user-story-recipe-expansion.md));
otherwise invent a recipe. Do not demote valid persona claims to unit-only._ · **17** stories

- [x] `fangore_completer_flavors`
- [x] `fangore_insp_exit_clean_state`
- [x] `fangore_insp_fan_in_policy`
- [x] `fangore_insp_handoff_record`
- [x] `fangore_insp_inference_capture_preflight`
- [x] `fangore_insp_loop_health`
- [x] `fangore_insp_operation_compensation`
- [x] `fangore_insp_risk_autonomy`
- [x] `fangore_insp_sparse_advisor`
- [x] `fangore_insp_state_governance`
- [x] `fangore_insp_stop_contract`
- [x] `fangore_insp_verification_gate`
- [x] `fangore_insp_wip_backpressure`
- [x] `nubble_insp_coordination_cost`
- [x] `nubble_insp_environment_delta`
- [x] `nubble_insp_resume_cost`
- [x] `nubble_topology_efficiency`

## Related

- [User-story recipe expansion](./user-story-recipe-expansion.md) — Wave 4+ working groups
- [User-story instrumentation migration](./user-story-instrumentation-migration.md)
- [`.cursor/skills/user-stories/SKILL.md`](../../.cursor/skills/user-stories/SKILL.md)
- [`docs/reference/cli-universe.md`](../reference/cli-universe.md)
- `tests/stories/scenarios/user_story_scenario.py`

