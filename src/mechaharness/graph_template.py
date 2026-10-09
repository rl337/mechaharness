"""Compatibility shim — prefer ``mechaharness.graph_templates``.

Deprecated public import path. Update call sites to the package when practical.
"""

from mechaharness.graph_templates import (
    BoundedRetryTemplate,
    DecisionPlaneTemplate,
    EnvironmentRepairTemplate,
    FanOutAggregateTemplate,
    GraphTemplate,
    GraphTemplateParams,
    GraphTemplateRegistry,
    IndependentReviewTemplate,
    SoftPoint,
    SubgraphNodeRunner,
    VerifyRepairTemplate,
    default_graph_templates,
    make_node,
)

__all__ = [
    "BoundedRetryTemplate",
    "DecisionPlaneTemplate",
    "EnvironmentRepairTemplate",
    "FanOutAggregateTemplate",
    "GraphTemplate",
    "GraphTemplateParams",
    "GraphTemplateRegistry",
    "IndependentReviewTemplate",
    "SoftPoint",
    "SubgraphNodeRunner",
    "VerifyRepairTemplate",
    "default_graph_templates",
    "make_node",
]
