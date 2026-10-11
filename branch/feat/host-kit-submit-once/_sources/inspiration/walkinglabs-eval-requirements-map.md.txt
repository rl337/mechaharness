# WalkingLabs + eval research requirements map

Maps backlog items from
[walkinglabs-harness-engineering-inspiration.md](./walkinglabs-harness-engineering-inspiration.md)
and [eval-research.md](./eval-research.md) to modules and user stories.

**Coverage:** *story* means a persona story exercises the path; *surface* means
types exist with unit/doctest coverage. S1 (attribution repair targets) was
delivered with WL-P0-5.

| ID | Topic | Modules | Library | Story |
|----|-------|---------|---------|-------|
| WL-P0-1 | Model-input replay manifest | `model_input_manifest.py` | story | `nubble_insp_model_input_replay` |
| WL-P0-2 | Graph transitions ≠ deps | `graph_transition.py` | story | `fangore_insp_graph_transitions` |
| WL-P0-3 | Isolation + template I/O | `isolation_contract.py` | story | `fangore_insp_isolation_io` |
| WL-P0-4 | Shared vs private context | `context_layers.py` | story | `fangore_insp_context_layers` |
| WL-P0-5 | Targeted rollback | `failure_attribution.py`, `graph_transition.py` | story | `fangore_insp_targeted_rollback` |
| WL-P0-6 | Approval interrupt | `approval_interrupt.py` | story | `fangore_insp_approval_interrupt` |
| WL-P0-7 | Trace envelope | `trace_envelope.py` | story | `nubble_insp_trace_envelope` |
| EVAL-1 | Evidence + claims | `eval_evidence.py` | story | `taloneth_insp_eval_claims` |
| EVAL-2 | Evaluator protocol | `evaluator.py` | story | `taloneth_insp_evaluator_compose` |
| EVAL-3 | Trial / pass@k / pass^k | `eval_trial.py` | story | `taloneth_insp_trial_reliability` |
| WL-P1-8 | WIP back-pressure | `work_in_progress_policy.py` | story | `fangore_insp_wip_backpressure` |
| WL-P1-9 | Fan-in acceptance | `fan_in_policy.py` | story | `fangore_insp_fan_in_policy` |
| WL-P1-10 | Exit / clean-state | `exit_contract.py` | story | `fangore_insp_exit_clean_state` |
| WL-P1-11 | Workspace isolation seam | `workspace_isolation.py` | story | `nubble_insp_workspace_isolation` |
| WL-P1-12 | Staged context compaction | `context_compaction.py` | story | `fangore_insp_context_compaction` |
| WL-P1-13 | State-field governance | `graph_state_governance.py` | story | `fangore_insp_state_governance` |
| WL-P1-14 | Anchor evidence | `anchor_evidence.py` | story | `fangore_insp_anchor_evidence` |
| WL-P2-15 | Component ablation | `component_ablation.py` | story | `taloneth_insp_component_ablation` |
| WL-P2-16 | Resume-cost telemetry | `resume_cost.py` | story | `nubble_insp_resume_cost` |
| WL-P2-17 | Coordination-cost telemetry | `coordination_cost.py` | story | `nubble_insp_coordination_cost` |
| WL-P2-18 | Loop health | `loop_health.py` | story | `fangore_insp_loop_health` |
| WL-P2-19 | Harness health snapshot | `harness_health.py` | story | `taloneth_insp_harness_health` |
| WL-P2-20 | Rule promotion records | `rule_promotion.py` | story | `taloneth_insp_rule_promotion` |
| WL-S2 | Instruction scope metadata | `instruction_component.py` | story | `fangore_insp_instruction_scope` |
| WL-S3 | Initialize preflight template | `graph_templates/initialize_preflight.py` | story | `fangore_insp_initialize_preflight` |
| WL-S4 | HandoffRecord | `handoff_record.py` | story | `fangore_insp_handoff_record` |
| WL-S5 | Operation compensation | `operation_registry.py` | story | `fangore_insp_operation_compensation` |
| WL-S6 | Environment deltas | `environment_delta.py` | story | `nubble_insp_environment_delta` |

## Attribution

Follow-on work must keep the **exact WalkingLabs / Anthropic / arXiv permalink**
in story footnotes (see each `story.json`), not only a link to the aggregate
inspiration documents.
