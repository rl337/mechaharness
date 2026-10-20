"""Interim domain harnesses: former kind strings become ``request.op`` values."""

from __future__ import annotations

from tests.stories.harness.base import OpDispatchHarness
from tests.stories.runners.access_authority import RUNNERS as ACCESS_AUTHORITY_OPS
from tests.stories.runners.graph_recipes import RUNNERS as GRAPH_RECIPES_OPS
from tests.stories.runners.lifecycle_extensions import RUNNERS as LIFECYCLE_EXTENSIONS_OPS

ACCESS_AUTHORITY = OpDispatchHarness("access_authority", ACCESS_AUTHORITY_OPS)
GRAPH_RECIPES = OpDispatchHarness("graph_recipes", GRAPH_RECIPES_OPS)
LIFECYCLE_EXTENSIONS = OpDispatchHarness("lifecycle_extensions", LIFECYCLE_EXTENSIONS_OPS)

DOMAIN_HARNESSES = (
    ACCESS_AUTHORITY,
    GRAPH_RECIPES,
    LIFECYCLE_EXTENSIONS,
)

# Former story kind → (harness family, op) for fixture migration.
KIND_TO_HARNESS_OP: dict[str, tuple[str, str]] = {}
for _h in DOMAIN_HARNESSES:
    for _op in _h.ops:
        KIND_TO_HARNESS_OP[_op] = (_h.name, _op)
