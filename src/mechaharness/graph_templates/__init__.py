"""Parameterized graph templates — library-owned reusable subgraph skeletons.

Import from this package. The legacy module ``mechaharness.graph_template``
re-exports the same public surface for compatibility.
"""

from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    GraphTemplateRegistry,
    SoftPoint,
    SubgraphNodeRunner,
    make_node,
)
from mechaharness.graph_templates.catalog import default_graph_templates
from mechaharness.graph_templates.environment_repair import EnvironmentRepairTemplate
from mechaharness.graph_templates.fan_out_aggregate import FanOutAggregateTemplate
from mechaharness.graph_templates.independent_review import IndependentReviewTemplate
from mechaharness.graph_templates.verify_repair import VerifyRepairTemplate

__all__ = [
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
