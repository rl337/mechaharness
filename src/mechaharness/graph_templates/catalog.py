"""Default library catalog of parameterized graph templates / Agentic Recipes.

Membership is a class map consumed by pyiv ``contribute_map`` /
``catalog_keys`` via :meth:`MechaHarnessConfig.graph_template_classes`.
``default_graph_templates()`` is the non-DI facade over the same map.
"""

from __future__ import annotations

from mechaharness.graph_templates.audited_infer_accept import AuditedInferAcceptTemplate
from mechaharness.graph_templates.backend_describe import BackendDescribeTemplate
from mechaharness.graph_templates.base import GraphTemplate, GraphTemplateRegistry
from mechaharness.graph_templates.bounded_retry import BoundedRetryTemplate
from mechaharness.graph_templates.change_decomposition import (
    ChangeDecompositionTemplate,
)
from mechaharness.graph_templates.change_execution import ChangeExecutionTemplate
from mechaharness.graph_templates.change_verification import ChangeVerificationTemplate
from mechaharness.graph_templates.context_pack import ContextPackTemplate
from mechaharness.graph_templates.contract_extraction import ContractExtractionTemplate
from mechaharness.graph_templates.conversational_tool_loop import (
    ConversationalToolLoopTemplate,
)
from mechaharness.graph_templates.decision_plane import DecisionPlaneTemplate
from mechaharness.graph_templates.demo_guidance import DemoGuidanceTemplate
from mechaharness.graph_templates.environment_repair import EnvironmentRepairTemplate
from mechaharness.graph_templates.failure_diagnosis import FailureDiagnosisTemplate
from mechaharness.graph_templates.fan_out_aggregate import FanOutAggregateTemplate
from mechaharness.graph_templates.gastronomic_guided_development import (
    GastronomicGuidedDevelopmentTemplate,
)
from mechaharness.graph_templates.guided_coding import GuidedCodingTemplate
from mechaharness.graph_templates.harness_run import HarnessRunTemplate
from mechaharness.graph_templates.independent_review import IndependentReviewTemplate
from mechaharness.graph_templates.initialize_preflight import InitializePreflightTemplate
from mechaharness.graph_templates.instruction_todo_plan import InstructionTodoPlanTemplate
from mechaharness.graph_templates.produce_critique_refine import (
    ProduceCritiqueRefineTemplate,
)
from mechaharness.graph_templates.safety_eval import SafetyEvalTemplate
from mechaharness.graph_templates.verify_repair import VerifyRepairTemplate
from mechaharness.graph_templates.workspace_discovery import WorkspaceDiscoveryTemplate


def default_graph_template_classes() -> dict[str, type[GraphTemplate]]:
    """Catalog id → template class (single source of recipe membership)."""
    return {
        FanOutAggregateTemplate.name: FanOutAggregateTemplate,
        DemoGuidanceTemplate.name: DemoGuidanceTemplate,
        VerifyRepairTemplate.name: VerifyRepairTemplate,
        WorkspaceDiscoveryTemplate.name: WorkspaceDiscoveryTemplate,
        ContractExtractionTemplate.name: ContractExtractionTemplate,
        ChangeDecompositionTemplate.name: ChangeDecompositionTemplate,
        ChangeExecutionTemplate.name: ChangeExecutionTemplate,
        ChangeVerificationTemplate.name: ChangeVerificationTemplate,
        FailureDiagnosisTemplate.name: FailureDiagnosisTemplate,
        GastronomicGuidedDevelopmentTemplate.name: GastronomicGuidedDevelopmentTemplate,
        IndependentReviewTemplate.name: IndependentReviewTemplate,
        EnvironmentRepairTemplate.name: EnvironmentRepairTemplate,
        InitializePreflightTemplate.name: InitializePreflightTemplate,
        DecisionPlaneTemplate.name: DecisionPlaneTemplate,
        ContextPackTemplate.name: ContextPackTemplate,
        BoundedRetryTemplate.name: BoundedRetryTemplate,
        ConversationalToolLoopTemplate.name: ConversationalToolLoopTemplate,
        AuditedInferAcceptTemplate.name: AuditedInferAcceptTemplate,
        InstructionTodoPlanTemplate.name: InstructionTodoPlanTemplate,
        GuidedCodingTemplate.name: GuidedCodingTemplate,
        HarnessRunTemplate.name: HarnessRunTemplate,
        BackendDescribeTemplate.name: BackendDescribeTemplate,
        ProduceCritiqueRefineTemplate.name: ProduceCritiqueRefineTemplate,
        SafetyEvalTemplate.name: SafetyEvalTemplate,
    }


def default_graph_templates() -> GraphTemplateRegistry:
    """Library-owned Agentic Recipes; clients bind soft points and may retain graphs."""
    return GraphTemplateRegistry(
        {name: cls() for name, cls in default_graph_template_classes().items()}
    )
