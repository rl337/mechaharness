# Personal agent reliability requirements map

Maps backlog items from
[personal-agent-reliability-inspiration.md](./personal-agent-reliability-inspiration.md)
(`MH-PA-*`) to modules and user stories.

**Coverage:** *story* means a persona story exercises an integrated library path;
*partial* means helpers/schemas ship but auto-wiring or host integration remains
open (see Gaps); *gap* means the product contract is not shipped. Inspiration
status: **proposal**, not an accepted requirement.

**Ownership:** MechaHarness owns reusable graph primitives, recipes, grants,
checkpoints, and audit envelopes. June owns personal identity, memory content,
scheduling, and proactive prioritization. home_network owns supporting
state/backup/health infrastructure.

| ID | Topic | Modules | Library | Story | Gaps |
|----|-------|---------|---------|-------|------|
| MH-PA-01 | Typed provenance and freshness | `core/types.py` (`ToolResult`), `tool_result_freshness.py`, `context_provider.py`, `decision_plane_runtime.py` | story | `fangore_jev_context_picker`, `fangore_insp_context_provider`, `fangore_insp_tool_result_freshness` | — |
| MH-PA-02 | Authority policy gate | `authority_gate.py`, `core/access.py`, `capability_envelope.py`, `consequence.py`, `judgement_policy.py`, `approval_interrupt.py` | story | `fangore_insp_risk_autonomy`, `fangore_jev_action_safety`, `fangore_compound_grants`, `fangore_insp_authority_gate` | — |
| MH-PA-03 | Recipe contracts | `graph_templates/` (`produce_critique_refine`), `isolation/isolation_contract.py`, `budget.py`, `stop_contract.py` | story | `fangore_insp_independent_review`, `fangore_verify_repair_recipe`, `fangore_insp_isolation_io`, `fangore_insp_produce_critique_refine` | Optional council recipe (non-default) not shipped |
| MH-PA-04 | Delegation and handoff | `handoff_record.py`, `delegation_policy.py`, `capability_envelope.py` | story | `fangore_insp_handoff_record` | — |
| MH-PA-05 | Checkpoint-compatible execution | `checkpoint_store.py`, `external_effect.py`, `graph_executor.py`, `approval_interrupt.py` | story | `fangore_transactional_durable_resume`, `fangore_insp_durable_resume` | — |
| MH-PA-06 | Deterministic alert/error rules | `alert_escalation.py`, `judgement_policy.py`, `decision_surfaces.py` (no `decision_plane` soft point) | partial | `fangore_decision_plane_policy`, `fangore_insp_alert_escalation_rules` | Hosts own durable alert counts; `AlertEscalationPolicy` is not auto-wired into the decision-plane runtime |
| MH-PA-07 | Correction-to-test feedback | `rule_promotion.py` (`PromotionRecord.record_id`, `SpecificationDebtLedger`; `specification_debt.py` is a shim), `failure_attribution.py` | partial | `taloneth_insp_rule_promotion`, `taloneth_insp_correction_spec_debt` | Host generates the regression test; the library ships the ledger schema and in-memory reference ledger only |
| MH-PA-08 | Observability and audit | `decision_log.py` (`ReviewAuditRecord`), `trace_envelope.py`, `event_correlators.py`, `tool_result_freshness.py`, `recipe_runner.py` | partial | `fangore_decision_plane_telemetry`, `nubble_insp_trace_envelope`, `nubble_insp_recipe_audit_dimensions`, `nubble_graph_event_correlators` | Graph lifecycle events now carry `graph_id`, recipe stamp, and `authorization_epoch` (OBS-A01..A06); audit fields on `DecisionRecord` / `TraceEnvelope` remain optional and caller-populated |

## Related inspirations

- [OpenAI Dots agent safety](./openai-dots-agent-safety-inspiration.md) — authority, revalidation, denial persistence
- [Self-revising recipe evolution](./self-revising-recipe-evolution.md) — recipe versioning and evaluation loops
