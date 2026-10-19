"""Blessed host imports for promoted inspiration surfaces (re-export catalog).

One import path for the authority, isolation, recipe-lifecycle, audit, and
correlator surfaces hosts build on. Nothing is defined here: each name lives in
its owning module (see ``docs/reference/inspiration-primitives.md``), so hosts
may equally import the leaf. Bind policies through ``MechaHarnessConfig`` hooks
(``get_authority_gate``, ``get_denial_store``, ``get_tool_result_freshness_policy``,
``get_recipe_promotion_policy``, ``get_evolution_campaign_hooks``) rather than
constructing them by hand; ``promote_recipe`` takes the Config-bound hooks::

    >>> from mechaharness.host_apis import (
    ...     NoopRecipePromotionPolicy, RecipePromotionRequest, host_authority_gate,
    ...     promote_recipe,
    ... )
    >>> host_authority_gate().evaluate(action="read").outcome
    'allow'
    >>> from mechaharness.graph_templates import default_graph_templates
    >>> registry = default_graph_templates()
    >>> promote_recipe(
    ...     registry,
    ...     NoopRecipePromotionPolicy(),
    ...     RecipePromotionRequest(recipe="verify_repair", to_version="1"),
    ... ).allowed
    False
"""

from __future__ import annotations

from mechaharness.alert_escalation import (
    AlertEscalationPolicy,
    AlertOccurrenceCounter,
)

# Authority and execution tokens (MH-DOTS-01/02/05, MH-PA-01/02)
from mechaharness.authority_gate import (
    AuthorityDecision,
    AuthorityGate,
)
from mechaharness.capability_envelope import (
    CapabilityEnvelope,
)
from mechaharness.decision_conflict_checkpoint import (
    neighbor_revisit,
    neighbors_from_write_conflicts,
)

# Review audit, correction debt, and alerts (MH-PA-06/07/08, MH-DOTS-09)
from mechaharness.decision_log import (
    DecisionRecord,
    RecipeAuditRow,
    ReviewAuditRecord,
    summarize_recipe_audit,
)
from mechaharness.denial_store import (
    DenialRecord,
    DenialStore,
    InMemoryDenialStore,
    equivalent_action_digest,
)
from mechaharness.effect_revalidation import (
    EffectRevalidation,
    revalidate_before_effect,
)

# Event correlators (OBS-A01..A06)
from mechaharness.event_correlators import (
    GRAPH_CORRELATOR_KEYS,
    NodeAttemptRow,
    graph_trace_context,
    project_node_attempt_rows,
)
from mechaharness.handoff_record import (
    HandoffRecord,
)

# Host kit (DI-first wiring)
from mechaharness.host_kit import (
    host_authority_gate,
    host_denial_store,
    host_graph_executor,
)

# Isolation and handoff (MH-DOTS-07)
from mechaharness.isolation import (
    CrossTaskIsolationGuard,
    InMemoryWorkspaceIsolationProvider,
    IsolationContract,
    IsolationViolation,
    TemplateIOContract,
    WorkspaceIsolationProvider,
)
from mechaharness.operation_registry import (
    ToolPhase,
    assert_tool_phase_allows_effects,
)

# Recipe lifecycle (MH-SR-04..09)
from mechaharness.recipe_lifecycle import (
    EvolutionCampaignHooks,
    NoopEvolutionCampaignHooks,
    NoopRecipePromotionPolicy,
    RecipePromotionDecision,
    RecipePromotionPolicy,
    RecipePromotionRequest,
    promote_recipe,
    propose_candidates,
    search_compatible_recipes,
    select_candidate,
    validate_candidate,
)
from mechaharness.rule_promotion import (
    PromotionRecord,
    SpecificationDebtLedger,
    SpecificationDebtRecord,
    capture_correction,
)
from mechaharness.tool_result_freshness import (
    ToolResultFreshnessPolicy,
    is_stale,
    reject_if_stale,
)
from mechaharness.trace_envelope import (
    TraceEnvelope,
)

__all__ = [
    "AlertEscalationPolicy",
    "AlertOccurrenceCounter",
    "AuthorityDecision",
    "AuthorityGate",
    "CapabilityEnvelope",
    "CrossTaskIsolationGuard",
    "DecisionRecord",
    "DenialRecord",
    "DenialStore",
    "EffectRevalidation",
    "EvolutionCampaignHooks",
    "GRAPH_CORRELATOR_KEYS",
    "HandoffRecord",
    "InMemoryDenialStore",
    "InMemoryWorkspaceIsolationProvider",
    "IsolationContract",
    "IsolationViolation",
    "NodeAttemptRow",
    "NoopEvolutionCampaignHooks",
    "NoopRecipePromotionPolicy",
    "PromotionRecord",
    "RecipeAuditRow",
    "RecipePromotionDecision",
    "RecipePromotionPolicy",
    "RecipePromotionRequest",
    "ReviewAuditRecord",
    "SpecificationDebtLedger",
    "SpecificationDebtRecord",
    "TemplateIOContract",
    "ToolPhase",
    "ToolResultFreshnessPolicy",
    "TraceEnvelope",
    "WorkspaceIsolationProvider",
    "assert_tool_phase_allows_effects",
    "capture_correction",
    "equivalent_action_digest",
    "graph_trace_context",
    "host_authority_gate",
    "host_denial_store",
    "host_graph_executor",
    "is_stale",
    "neighbor_revisit",
    "neighbors_from_write_conflicts",
    "project_node_attempt_rows",
    "promote_recipe",
    "propose_candidates",
    "reject_if_stale",
    "revalidate_before_effect",
    "search_compatible_recipes",
    "select_candidate",
    "summarize_recipe_audit",
    "validate_candidate",
]
