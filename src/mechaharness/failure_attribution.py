"""Structured failure attribution for traces (req 11)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FailureCategory = Literal[
    "graph_topology",
    "routing",
    "context",
    "tools",
    "models",
    "evaluator_policy",
    "linkage",
    "environment",
    "unknown",
]


class FailureAttribution(BaseModel):
    """Enough structure to attribute failures across runs."""

    model_config = ConfigDict(extra="allow")

    category: FailureCategory = "unknown"
    node_id: str | None = None
    kind: str | None = None
    error: str | None = None
    repeated_class: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    def to_event_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def attribute_error(error: str | None, *, node_id: str | None = None, kind: str | None = None) -> FailureAttribution:
    """Map common error prefixes to attribution categories."""
    text = error or ""
    category: FailureCategory = "unknown"
    if text.startswith("no_runner:") or text.startswith("linkage_failed"):
        category = "linkage"
    elif text.startswith("missing_grant") or text == "permission_denied":
        category = "tools"
    elif text.startswith("incompatible_checkpoint"):
        category = "graph_topology"
    elif "environment" in text:
        category = "environment"
    elif text.startswith("subgraph_"):
        category = "graph_topology"
    return FailureAttribution(
        category=category,
        node_id=node_id,
        kind=kind,
        error=error,
        repeated_class=text.split(":", 1)[0] if text else None,
    )


def detect_repeated_failure_classes(
    attributions: list[FailureAttribution],
    *,
    min_count: int = 2,
) -> list[str]:
    counts: dict[str, int] = {}
    for item in attributions:
        key = item.repeated_class or item.category
        counts[key] = counts.get(key, 0) + 1
    return sorted(k for k, n in counts.items() if n >= min_count)
