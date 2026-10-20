"""Surface GraphExecutor budget spend on probe observations.

NodeOutcome.cost_units charges into GraphResult.budget_spent. Story expects use
the same ``cost_units`` key as inference pricing so ``kind: lte`` ceilings apply
uniformly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def graph_cost_fields(*results: Any) -> dict[str, float]:
    """Sum ``budget_spent`` from one or more :class:`GraphResult`-like values."""
    spent = 0.0
    for result in results:
        if result is None:
            continue
        value = getattr(result, "budget_spent", None)
        if value is None and isinstance(result, Mapping):
            value = result.get("budget_spent")
        if value is not None:
            spent += float(value)
    return {"budget_spent": spent, "cost_units": spent}


def with_graph_cost(payload: Mapping[str, Any], *results: Any) -> dict[str, Any]:
    """Merge graph cost fields into a probe observation dict."""
    out = dict(payload)
    costs = graph_cost_fields(*results)
    # Explicit payload keys win (budget-focused stories may set their own).
    for key, value in costs.items():
        out.setdefault(key, value)
    return out
