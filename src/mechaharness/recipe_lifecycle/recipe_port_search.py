"""Typed-port search over registered recipes (MH-SR-04).

Composition candidates come only from the catalog: the search compares each
active recipe's declared :class:`~mechaharness.isolation.isolation_contract.TemplateIOContract`
against the ports the caller needs and returns **catalog ids**. It never
synthesizes a graph, a node, or an executable; recipes that declare no
``io_contract`` are simply not candidates::

    >>> from mechaharness.graph_templates import default_graph_templates
    >>> from mechaharness.recipe_lifecycle.recipe_port_search import search_compatible_recipes
    >>> registry = default_graph_templates()
    >>> search_compatible_recipes(
    ...     registry,
    ...     required_inputs={"scenario": "object"},
    ...     required_outputs={"safety_report": "object"},
    ... )
    ['safety_eval']

A recipe is compatible when it *accepts* every required input port and
*produces* every required output port with a matching type. The type
``"any"`` on either side matches anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mechaharness.graph_templates.base import GraphTemplateRegistry
from mechaharness.isolation.isolation_contract import TemplateIOContract

ANY_PORT_TYPE = "any"


def port_types_match(offered: Any, required: Any) -> bool:
    """Whether a declared port type satisfies a required one."""
    return offered == required or ANY_PORT_TYPE in (offered, required)


def ports_satisfied(
    declared: Mapping[str, Any], required: Mapping[str, Any]
) -> bool:
    """Every required port is declared with a compatible type."""
    return all(
        name in declared and port_types_match(declared[name], wanted)
        for name, wanted in required.items()
    )


def contract_is_compatible(
    contract: TemplateIOContract,
    *,
    required_inputs: Mapping[str, Any],
    required_outputs: Mapping[str, Any],
) -> bool:
    return ports_satisfied(contract.inputs, required_inputs) and ports_satisfied(
        contract.outputs, required_outputs
    )


def search_compatible_recipes(
    registry: GraphTemplateRegistry,
    required_inputs: Mapping[str, Any] | None = None,
    required_outputs: Mapping[str, Any] | None = None,
) -> list[str]:
    """Catalog ids of active recipes whose declared ports fit the request.

    ``required_inputs`` are ports the recipe must accept; ``required_outputs``
    are ports it must produce. Results are sorted for determinism. Demoted or
    deprecated recipes and recipes without an ``io_contract`` are skipped.
    """
    wanted_in = dict(required_inputs or {})
    wanted_out = dict(required_outputs or {})
    found: list[str] = []
    for name in registry.active_names():
        template = registry.get(name)
        contract = getattr(template, "io_contract", None)
        if contract is None:
            continue
        if contract_is_compatible(
            contract, required_inputs=wanted_in, required_outputs=wanted_out
        ):
            found.append(name)
    return sorted(found)
