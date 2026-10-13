"""Default library catalog of parameterized graph templates / Agentic Recipes.

Membership is a class map consumed by pyiv ``contribute_map`` /
``catalog_keys`` via :meth:`MechaHarnessConfig.graph_template_classes`.
``default_graph_templates()`` is the non-DI facade over the same map.
"""

from __future__ import annotations

from mechaharness.graph_templates.backend_describe import BackendDescribeTemplate
from mechaharness.graph_templates.base import GraphTemplate, GraphTemplateRegistry
from mechaharness.graph_templates.bounded_retry import BoundedRetryTemplate
from mechaharness.graph_templates.conversational_tool_loop import (
    ConversationalToolLoopTemplate,
)
from mechaharness.graph_templates.decision_plane import DecisionPlaneTemplate
from mechaharness.graph_templates.environment_repair import EnvironmentRepairTemplate
from mechaharness.graph_templates.fan_out_aggregate import FanOutAggregateTemplate
from mechaharness.graph_templates.harness_run import HarnessRunTemplate
from mechaharness.graph_templates.independent_review import IndependentReviewTemplate
from mechaharness.graph_templates.initialize_preflight import InitializePreflightTemplate
from mechaharness.graph_templates.verify_repair import VerifyRepairTemplate


def default_graph_template_classes() -> dict[str, type[GraphTemplate]]:
    """Catalog id → template class (single source of recipe membership)."""
    return {
        FanOutAggregateTemplate.name: FanOutAggregateTemplate,
        VerifyRepairTemplate.name: VerifyRepairTemplate,
        IndependentReviewTemplate.name: IndependentReviewTemplate,
        EnvironmentRepairTemplate.name: EnvironmentRepairTemplate,
        InitializePreflightTemplate.name: InitializePreflightTemplate,
        DecisionPlaneTemplate.name: DecisionPlaneTemplate,
        BoundedRetryTemplate.name: BoundedRetryTemplate,
        ConversationalToolLoopTemplate.name: ConversationalToolLoopTemplate,
        HarnessRunTemplate.name: HarnessRunTemplate,
        BackendDescribeTemplate.name: BackendDescribeTemplate,
    }


def default_graph_templates() -> GraphTemplateRegistry:
    """Library-owned Agentic Recipes; clients bind soft points and may retain graphs."""
    return GraphTemplateRegistry(
        {name: cls() for name, cls in default_graph_template_classes().items()}
    )
