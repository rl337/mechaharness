# OpenAI Dots agent safety requirements map

Maps backlog items from
[openai-dots-agent-safety-inspiration.md](./openai-dots-agent-safety-inspiration.md)
(`MH-DOTS-*`) to modules and user stories.

**Coverage:** *story* means a persona story exercises the native path; *partial*
means important acceptance remains open; *gap* means the product contract is
not shipped. Inspiration status: **proposal**, not an accepted requirement.

**Principle:** Persistent context must never imply persistent permission.

**Ownership:** MechaHarness owns enforceable graph execution, independent action
review, and resumable authorization seams. June owns goals, memory, and
user-facing policy configuration.

| ID | Topic | Modules | Library | Story | Gaps |
|----|-------|---------|---------|-------|------|
| MH-DOTS-01 | Capability-scoped execution token | `capability_envelope.py`, `core/access.py`, `delegation_policy.py` | partial | `fangore_insp_capability_envelope`, `fangore_capability_envelope_narrow`, `fangore_insp_execution_token` | Principal, expiry, trust origin, authorization epoch on the token |
| MH-DOTS-02 | Revalidate before consequential side effects | `linkage_resolver.py`, `graph_executor.py`, `approval_interrupt.py`, `judgement_policy.py` | partial | `fangore_insp_wake_reresolve`, `fangore_human_review_pending`, `fangore_insp_effect_revalidation` | Mandatory pre-effect revalidation for all consequential tools after revocation |
| MH-DOTS-03 | Observe / Prepare / Execute tool classes | `external_effect.py`, `lifecycle_extension.py`, `operation_registry.py`, `tools/base.py` | gap | `fangore_insp_tool_effect_classes` | Tool-class taxonomy enforcing mutate-only-in-Execute |
| MH-DOTS-04 | Independent action review | `judgement_policy.py`, `decision_plane_runtime.py`, `approval_interrupt.py` | story | `fangore_jev_action_safety`, `fangore_human_review_pending` | — |
| MH-DOTS-05 | Denial persistence / equivalent-action detection | — (adjacent: `AccessControl`, `Verdict`) | gap | `fangore_insp_denial_equivalence` | Durable denial memory and equivalence across providers/tools |
| MH-DOTS-06 | Checkpoint and replay safety (auth epoch) | `checkpoint_store.py`, `sqlite_checkpoint_store.py`, `external_effect.py`, `host_kit.py` | partial | `fangore_transactional_durable_resume`, `fangore_insp_auth_epoch_resume` | Auth-epoch / grant-revocation epoch on replay |
| MH-DOTS-07 | Cross-task context isolation | `isolation_contract.py`, `workspace_isolation.py`, `handoff_record.py` | partial | `fangore_insp_isolation_io`, `fangore_insp_handoff_record`, `fangore_insp_cross_task_isolation` | Hard multi-task runtime boundary + intervening-task bleed tests |
| MH-DOTS-08 | Safety evaluation recipes | `eval_matrix.py`, `evaluator.py`, `graph_templates/independent_review.py` | gap | `taloneth_insp_safety_eval_recipes` | Dedicated safety-eval Agentic Recipe / fixture pack |
| MH-DOTS-09 | Review observability | `decision_log.py`, `trace_envelope.py`, `trace_reconciliation.py` | partial | `taloneth_policy_replay`, `nubble_insp_trace_reconciliation`, `nubble_insp_review_audit_reconstruct` | Unified review-audit record tying policy, approvals, denials, effects |

## Related inspirations

- [Personal agent reliability](./personal-agent-reliability-inspiration.md) — authority gate, checkpoints, audit
- [Self-revising recipe evolution](./self-revising-recipe-evolution.md) — evaluation recipes and promotion gates
