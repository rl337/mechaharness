"""Parameterized graph templates — Agentic Recipe substrate.

Import from this package. The legacy module ``mechaharness.graph_template``
re-exports the same public surface for compatibility.

Concrete catalog entries are **Agentic Recipes**: reusable control subgraphs
on :class:`GraphTemplate`. Soft points keep client bindings out of the library
skeleton::

    >>> from mechaharness.graph_templates import (
    ...     DecisionPlaneTemplate, GraphTemplateParams,
    ...     default_graph_templates,
    ... )
    >>> names = default_graph_templates().names()
    >>> "decision_plane" in names and "bounded_retry" in names
    True
    >>> plane = DecisionPlaneTemplate().instantiate(GraphTemplateParams(
    ...     goal="triage",
    ...     inputs={
    ...         "state_projection": {"ticket": "T-1"},
    ...         "facts": {"duplicate": True},
    ...         "questions": [{"id": "team", "kind": "choice",
    ...                        "options": ["billing"], "allowed_actions": ["billing"]}],
    ...     },
    ... ))
    >>> plane.template_name
    'decision_plane'
    >>> sorted(plane.nodes)  # doctest: +SKIP
    ['apply_policy', 'ask_batch', 'escalate', 'project_state']
"""

from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    GraphTemplateRegistry,
    SoftPoint,
    SubgraphNodeRunner,
    make_node,
    namespace_graph,
)
from mechaharness.graph_templates.bounded_retry import BoundedRetryTemplate
from mechaharness.graph_templates.catalog import default_graph_templates
from mechaharness.graph_templates.decision_plane import DecisionPlaneTemplate
from mechaharness.graph_templates.environment_repair import EnvironmentRepairTemplate
from mechaharness.graph_templates.fan_out_aggregate import FanOutAggregateTemplate
from mechaharness.graph_templates.independent_review import IndependentReviewTemplate
from mechaharness.graph_templates.initialize_preflight import InitializePreflightTemplate
from mechaharness.graph_templates.verify_repair import VerifyRepairTemplate

__all__ = [
    "BoundedRetryTemplate",
    "DecisionPlaneTemplate",
    "EnvironmentRepairTemplate",
    "FanOutAggregateTemplate",
    "GraphTemplate",
    "GraphTemplateParams",
    "GraphTemplateRegistry",
    "IndependentReviewTemplate",
    "InitializePreflightTemplate",
    "SoftPoint",
    "SubgraphNodeRunner",
    "VerifyRepairTemplate",
    "default_graph_templates",
    "make_node",
    "namespace_graph",
]
