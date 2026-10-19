"""Interim domain harnesses: former kind strings become ``request.op`` values."""

from __future__ import annotations

from tests.stories.harness.base import OpDispatchHarness
from tests.stories.runners.access_authority import RUNNERS as ACCESS_AUTHORITY_OPS
from tests.stories.runners.context_management import RUNNERS as CONTEXT_MANAGEMENT_OPS
from tests.stories.runners.decision_plane import RUNNERS as DECISION_PLANE_OPS
from tests.stories.runners.evaluation_research import RUNNERS as EVALUATION_RESEARCH_OPS
from tests.stories.runners.graph_execution import RUNNERS as GRAPH_EXECUTION_OPS
from tests.stories.runners.graph_recipes import RUNNERS as GRAPH_RECIPES_OPS
from tests.stories.runners.lifecycle_extensions import RUNNERS as LIFECYCLE_EXTENSIONS_OPS

ACCESS_AUTHORITY = OpDispatchHarness("access_authority", ACCESS_AUTHORITY_OPS)
CONTEXT_MANAGEMENT = OpDispatchHarness("context_management", CONTEXT_MANAGEMENT_OPS)
DECISION_PLANE = OpDispatchHarness("decision_plane", DECISION_PLANE_OPS)
EVALUATION_RESEARCH = OpDispatchHarness("evaluation_research", EVALUATION_RESEARCH_OPS)
GRAPH_EXECUTION = OpDispatchHarness("graph_execution", GRAPH_EXECUTION_OPS)
GRAPH_RECIPES = OpDispatchHarness("graph_recipes", GRAPH_RECIPES_OPS)
LIFECYCLE_EXTENSIONS = OpDispatchHarness("lifecycle_extensions", LIFECYCLE_EXTENSIONS_OPS)

DOMAIN_HARNESSES = (
    ACCESS_AUTHORITY,
    CONTEXT_MANAGEMENT,
    DECISION_PLANE,
    EVALUATION_RESEARCH,
    GRAPH_EXECUTION,
    GRAPH_RECIPES,
    LIFECYCLE_EXTENSIONS,
)

# Former story kind → (harness family, op) for fixture migration.
KIND_TO_HARNESS_OP: dict[str, tuple[str, str]] = {}
for _h in DOMAIN_HARNESSES:
    for _op in _h.ops:
        KIND_TO_HARNESS_OP[_op] = (_h.name, _op)
