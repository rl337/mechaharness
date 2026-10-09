"""Default library catalog of parameterized graph templates / Agentic Recipes."""

from __future__ import annotations

from mechaharness.graph_templates.base import GraphTemplateRegistry
from mechaharness.graph_templates.bounded_retry import BoundedRetryTemplate
from mechaharness.graph_templates.decision_plane import DecisionPlaneTemplate
from mechaharness.graph_templates.environment_repair import EnvironmentRepairTemplate
from mechaharness.graph_templates.fan_out_aggregate import FanOutAggregateTemplate
from mechaharness.graph_templates.independent_review import IndependentReviewTemplate
from mechaharness.graph_templates.initialize_preflight import InitializePreflightTemplate
from mechaharness.graph_templates.verify_repair import VerifyRepairTemplate


def default_graph_templates() -> GraphTemplateRegistry:
    """Library-owned Agentic Recipes; clients bind soft points and may retain graphs."""
    return GraphTemplateRegistry(
        [
            FanOutAggregateTemplate(),
            VerifyRepairTemplate(),
            IndependentReviewTemplate(),
            EnvironmentRepairTemplate(),
            InitializePreflightTemplate(),
            DecisionPlaneTemplate(),
            BoundedRetryTemplate(),
        ]
    )
