# Inspiration primitives (host import guide)

Blessed imports for surfaces promoted from inspiration maps (PA / DOTS / SR /
WalkingLabs / Jev / FineEnvs). Prefer `mechaharness.host_apis` when present;
otherwise import the leaf listed below. Inspiration maps under
[`docs/inspiration/`](../inspiration/) stay proposals until product requirements
absorb them.

| Leaf / surface | Map IDs | DI Config hook? | Import |
|----------------|---------|-----------------|--------|
| `CapabilityEnvelope` token fields | MH-DOTS-01, req 7 | via envelope on runs | `capability_envelope` / `host_apis` |
| `AuthorityGate` | MH-PA-02 | `get_authority_gate()` | `authority_gate` / `host_apis` |
| `DenialStore` | MH-DOTS-05 | `get_denial_store()` | `denial_store` / `host_apis` |
| Tool phase O/P/E | MH-DOTS-03 | on `Tool` / contracts | `operation_registry` / `host_apis` (`tool_phase` shim) |
| Effect revalidation | MH-DOTS-02 | used by `GraphExecutor`; shares `CapabilityEnvelope.authority_issue` with `AuthorityGate` | `effect_revalidation` |
| Tool result freshness | MH-PA-01 | `get_tool_result_freshness_policy()` | `tool_result_freshness` |
| Cross-task isolation | MH-DOTS-07 | helper | `isolation` / `host_apis` |
| Alert escalation | MH-PA-06 | host-driven helper (no soft point) | `alert_escalation` / `host_apis` |
| Specification debt | MH-PA-07 | schema | `rule_promotion` / `host_apis` (`specification_debt` shim) |
| Decision conflict helpers | MH-SR-08 | host-driven | `decision_conflict_checkpoint` |
| Recipe evolution / port search / promote | MH-SR-04..07, 09 | `get_recipe_promotion_policy()`, `get_evolution_campaign_hooks()` | `recipe_lifecycle` / `host_apis` |
| Review audit | MH-PA-08, MH-DOTS-09 | caller-populated | `decision_log` / `host_apis` (`review_audit` shim) |
| `produce_critique_refine` | MH-PA-03 | catalog | `graph_templates` |
| `safety_eval` | MH-DOTS-08 | catalog | `graph_templates` |

See also [Event analytics schema](../requirements/event-analytics-schema.md) for
warehouse-oriented correlators on EventLog emits.
