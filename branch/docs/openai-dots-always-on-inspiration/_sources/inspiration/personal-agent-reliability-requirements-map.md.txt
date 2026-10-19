# Personal agent reliability requirements map

Maps backlog items from
[personal-agent-reliability-inspiration.md](./personal-agent-reliability-inspiration.md)
(`MH-PA-*`) to modules and user stories.

**Coverage:** *story* means a persona story exercises the native path; *partial*
means important acceptance remains open; *gap* means the product contract is
not shipped. Inspiration status: **proposal**, not an accepted requirement.

**Ownership:** MechaHarness owns reusable graph primitives, recipes, grants,
checkpoints, and audit envelopes. June owns personal identity, memory content,
scheduling, and proactive prioritization. home_network owns supporting
state/backup/health infrastructure.

| ID | Topic | Modules | Library | Story | Gaps |
|----|-------|---------|---------|-------|------|
| MH-PA-01 | Typed provenance and freshness | `core/types.py` (`ToolResult`), `context_provider.py`, `decision_plane_runtime.py` | partial | `fangore_jev_context_picker`, `fangore_insp_context_provider`, `fangore_insp_tool_result_freshness` | Tool-result TTL / stale reject not first-class on harness `ToolResult` |
| MH-PA-02 | Authority policy gate | `core/access.py`, `capability_envelope.py`, `consequence.py`, `judgement_policy.py`, `approval_interrupt.py` | partial | `fangore_insp_risk_autonomy`, `fangore_jev_action_safety`, `fangore_compound_grants`, `fangore_insp_authority_gate` | No single gate composing capability + reversibility + impact + source trust + approval |
| MH-PA-03 | Recipe contracts | `graph_templates/`, `isolation_contract.py`, `budget.py`, `stop_contract.py` | partial | `fangore_insp_independent_review`, `fangore_verify_repair_recipe`, `fangore_insp_isolation_io`, `fangore_insp_produce_critique_refine` | Named produce-critique-refine / optional council recipes and applicability predicates |
| MH-PA-04 | Delegation and handoff | `handoff_record.py`, `delegation_policy.py`, `capability_envelope.py` | partial | `fangore_insp_handoff_record` | Goals, exclusions, and verdict schema not first-class (only via `detail`) |
| MH-PA-05 | Checkpoint-compatible execution | `checkpoint_store.py`, `external_effect.py`, `graph_executor.py`, `approval_interrupt.py` | story | `fangore_transactional_durable_resume`, `fangore_insp_durable_resume` | — |
| MH-PA-06 | Deterministic alert/error rules | `judgement_policy.py`, `decision_surfaces.py`, `decision_plane_runtime.py` | partial | `fangore_decision_plane_policy`, `fangore_insp_alert_escalation_rules` | Alert escalation catalog (once/log → repeated/surface → persistent/propose) |
| MH-PA-07 | Correction-to-test feedback | `rule_promotion.py`, `failure_attribution.py` | partial | `taloneth_insp_rule_promotion`, `taloneth_insp_correction_spec_debt` | Correction → generated-test / specification-debt ledger |
| MH-PA-08 | Observability and audit | `decision_log.py`, `trace_envelope.py`, `recipe_runner.py` | partial | `fangore_decision_plane_telemetry`, `nubble_insp_trace_envelope`, `nubble_insp_recipe_audit_dimensions` | Recipe-selection and freshness as first-class audit dimensions |

## Related inspirations

- [OpenAI Dots agent safety](./openai-dots-agent-safety-inspiration.md) — authority, revalidation, denial persistence
- [Self-revising recipe evolution](./self-revising-recipe-evolution.md) — recipe versioning and evaluation loops
