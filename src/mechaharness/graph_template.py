"""Compatibility shim — prefer ``mechaharness.graph_templates``.

Deprecated public import path. Update call sites to the package when practical.
Re-exports the package's full public surface so old imports keep working.
"""

from mechaharness.graph_templates import (
    BackendDescribeTemplate,
    BoundedRetryTemplate,
    ConversationalToolLoopTemplate,
    DecisionPlaneTemplate,
    EnvironmentRepairTemplate,
    FanOutAggregateTemplate,
    GraphTemplate,
    GraphTemplateParams,
    GraphTemplateRegistry,
    HarnessRunTemplate,
    IndependentReviewTemplate,
    InitializePreflightTemplate,
    ProduceCritiqueRefineTemplate,
    SafetyEvalTemplate,
    SoftPoint,
    SubgraphNodeRunner,
    VerifyRepairTemplate,
    default_graph_template_classes,
    default_graph_templates,
    make_node,
    namespace_graph,
)

__all__ = [
    "BackendDescribeTemplate",
    "BoundedRetryTemplate",
    "ConversationalToolLoopTemplate",
    "DecisionPlaneTemplate",
    "EnvironmentRepairTemplate",
    "FanOutAggregateTemplate",
    "GraphTemplate",
    "GraphTemplateParams",
    "GraphTemplateRegistry",
    "HarnessRunTemplate",
    "IndependentReviewTemplate",
    "InitializePreflightTemplate",
    "ProduceCritiqueRefineTemplate",
    "SafetyEvalTemplate",
    "SoftPoint",
    "SubgraphNodeRunner",
    "VerifyRepairTemplate",
    "default_graph_template_classes",
    "default_graph_templates",
    "make_node",
    "namespace_graph",
]
