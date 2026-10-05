"""Parameterized graph templates — library-owned reusable subgraph skeletons.

Import from this package. The legacy module ``mechaharness.graph_template``
re-exports the same public surface for compatibility.

In *A harness for every task: dynamic workflows in Claude Code*, the Claude
developer blog suggests composing reusable shapes such as fan-out-and-
synthesize, loop-until-done, and adversarial verification
(https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code).
In *Continually improving our agent harness*, the Cursor developer blog
suggests keeping harness scaffolding revisable rather than permanently
embedding one product's workflow
(https://cursor.com/blog/continually-improving-agent-harness).
Soft points keep client bindings out of the library skeleton::

    >>> from mechaharness.graph_templates import (
    ...     FanOutAggregateTemplate, GraphTemplateParams,
    ...     IndependentReviewTemplate, VerifyRepairTemplate,
    ...     default_graph_templates,
    ... )
    >>> names = default_graph_templates().names()
    >>> "fan_out_aggregate" in names and "verify_repair" in names
    True
    >>> fan = FanOutAggregateTemplate().instantiate(GraphTemplateParams(
    ...     goal="bug hunt across auth and billing",
    ...     branch_payloads=[{"area": "auth"}, {"area": "billing"}],
    ...     soft_bindings={"branch_kind": "explore"},
    ...     source_workflow_ref="acme:overnight_audit_v2",
    ... ))
    >>> [n for n in sorted(fan.nodes) if n.startswith("branch")]
    ['branch_0', 'branch_1']
    >>> fan.source_workflow_ref
    'acme:overnight_audit_v2'
    >>> VerifyRepairTemplate().describe()["name"]
    'verify_repair'
    >>> IndependentReviewTemplate().soft_points[4].name
    'omit_producer_reasoning'
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
from mechaharness.graph_templates.initialize_preflight import InitializePreflightTemplate
from mechaharness.graph_templates.verify_repair import VerifyRepairTemplate

__all__ = [
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
]
