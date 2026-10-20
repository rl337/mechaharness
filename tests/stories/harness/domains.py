"""Interim domain harnesses: former kind strings become ``request.op`` values."""

from __future__ import annotations

from tests.stories.harness.base import OpDispatchHarness
from tests.stories.runners.graph_recipes import RUNNERS as GRAPH_RECIPES_OPS

GRAPH_RECIPES = OpDispatchHarness("graph_recipes", GRAPH_RECIPES_OPS)

DOMAIN_HARNESSES = (
    GRAPH_RECIPES,
)

# Former story kind → (harness family, op) for fixture migration.
KIND_TO_HARNESS_OP: dict[str, tuple[str, str]] = {}
for _h in DOMAIN_HARNESSES:
    for _op in _h.ops:
        KIND_TO_HARNESS_OP[_op] = (_h.name, _op)
