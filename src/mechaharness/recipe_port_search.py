"""Compatibility shim — prefer ``mechaharness.recipe_lifecycle.recipe_port_search``.

Deprecated public import path. Update call sites to the package when practical.
"""

from mechaharness.recipe_lifecycle.recipe_port_search import (
    ANY_PORT_TYPE,
    contract_is_compatible,
    port_types_match,
    ports_satisfied,
    search_compatible_recipes,
)

__all__ = [
    "ANY_PORT_TYPE",
    "port_types_match",
    "ports_satisfied",
    "contract_is_compatible",
    "search_compatible_recipes",
]
