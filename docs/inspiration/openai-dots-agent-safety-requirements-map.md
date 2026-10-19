# OpenAI Dots agent safety requirements map

Maps backlog items from
[openai-dots-agent-safety-inspiration.md](./openai-dots-agent-safety-inspiration.md)
(`MH-DOTS-*`) to modules and user stories.

**Coverage:** *story* means a persona story exercises an integrated library path;
*partial* means helpers/schemas ship but auto-wiring or host integration remains
open (see Gaps); *gap* means the product contract is not shipped. Inspiration
status: **proposal**, not an accepted requirement.

**Principle:** Persistent context must never imply persistent permission.

**Ownership:** MechaHarness owns enforceable graph execution, independent action
review, and resumable authorization seams. June owns goals, memory, and
user-facing policy configuration.

| ID | Topic | Modules | Library | Story | Gaps |
|----|-------|---------|---------|-------|------|
| MH-DOTS-01 | Capability-scoped execution token | `capability_envelope.py`, `core/access.py`, `delegation_policy.py` | story | `fangore_capability_envelope_narrow`, `fangore_insp_execution_token` | — |
| MH-DOTS-02 | Revalidate before consequential side effects | `effect_revalidation.py`, `graph_executor.py`, `linkage_resolver.py`, `approval_interrupt.py`, `judgement_policy.py` | story | `fangore_insp_wake_reresolve`, `fangore_human_review_pending`, `fangore_insp_effect_revalidation` | — |
| MH-DOTS-03 | Observe / Prepare / Execute tool classes | `operation_registry.py` (`ToolPhase`; `tool_phase.py` is a shim), `tools/base.py`, `external_effect.py` | story | `fangore_insp_tool_effect_classes` | — |
| MH-DOTS-04 | Independent action review | `judgement_policy.py`, `decision_plane_runtime.py`, `approval_interrupt.py` | story | `fangore_jev_action_safety`, `fangore_human_review_pending` | — |
| MH-DOTS-05 | Denial persistence / equivalent-action detection | `denial_store.py`, `authority_gate.py` | partial | `fangore_insp_denial_equivalence` | Restart-durable `DenialStore` is host-bound (in-memory reference ships) |
| MH-DOTS-06 | Checkpoint and replay safety (auth epoch) | `checkpoint_store.py`, `sqlite_checkpoint_store.py`, `graph_executor.py`, `external_effect.py`, `host_kit.py` | story | `fangore_transactional_durable_resume`, `fangore_insp_auth_epoch_resume` | — |
| MH-DOTS-07 | Cross-task context isolation | `isolation/cross_task_isolation.py`, `isolation/isolation_contract.py`, `isolation/workspace_isolation.py`, `handoff_record.py` | story | `fangore_insp_isolation_io`, `fangore_insp_handoff_record`, `fangore_insp_cross_task_isolation` | — |
| MH-DOTS-08 | Safety evaluation recipes | `graph_templates/safety_eval.py`, `eval_matrix.py`, `evaluator.py`, `graph_templates/independent_review.py` | partial | `taloneth_insp_safety_eval_recipes` | Ships the recipe and scenario-class vocabulary; hosts supply scenario corpora and node runners |
| MH-DOTS-09 | Review observability | `decision_log.py` (`ReviewAuditRecord`), `trace_envelope.py`, `event_correlators.py`, `trace_reconciliation.py` | partial | `taloneth_policy_replay`, `nubble_insp_trace_reconciliation`, `nubble_insp_review_audit_reconstruct`, `nubble_graph_event_correlators` | Source trust, delegated scope, and denial reasons are caller-attested; they are not auto-collected from the harness |

## Related inspirations

- [Personal agent reliability](./personal-agent-reliability-inspiration.md) — authority gate, checkpoints, audit
- [Self-revising recipe evolution](./self-revising-recipe-evolution.md) — evaluation recipes and promotion gates
