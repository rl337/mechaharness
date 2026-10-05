"""Durable graph-shared state versus node-private context projections.

WalkingLabs L14 distinguishes graph-shared state from node-private context;
L04 reinforces loading instructions/context close to where they apply
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/,
https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-04-why-one-giant-instruction-file-fails/).

Only explicit exports re-enter shared state::

    >>> from mechaharness.context_layers import (
    ...     GraphSharedState, NodePrivateContext, project_node_context,
    ... )
    >>> shared = GraphSharedState(data={"goal": "ship", "notes": ["a", "b"]})
    >>> private = project_node_context(shared, needs=["goal"], node_id="n1")
    >>> private.data
    {'goal': 'ship'}
    >>> _ = private.export_to_shared(shared, {"result": "ok"})
    >>> shared.data["result"]
    'ok'
    >>> "notes" in private.data
    False
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphSharedState(BaseModel):
    """Durable state shared across nodes; may exceed inference context size."""

    model_config = ConfigDict(extra="allow")

    data: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)


class NodePrivateContext(BaseModel):
    """Private projection assembled for one node inference step."""

    model_config = ConfigDict(extra="allow")

    node_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    instruction_refs: list[str] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)

    def export_to_shared(
        self, shared: GraphSharedState, exports: dict[str, Any]
    ) -> GraphSharedState:
        """Merge only explicitly exported keys back into shared state."""
        shared.data.update(exports)
        return shared


def project_node_context(
    shared: GraphSharedState,
    *,
    needs: list[str],
    node_id: str,
    instruction_refs: list[str] | None = None,
) -> NodePrivateContext:
    """Build a node-private projection from declared needs (map first, details on demand)."""
    data = {key: shared.data[key] for key in needs if key in shared.data}
    return NodePrivateContext(
        node_id=node_id,
        data=data,
        instruction_refs=list(instruction_refs or ()),
        source_keys=list(data.keys()),
    )


class ContextLayerProjection(BaseModel):
    """Named projection policy for assembling node context from shared state."""

    model_config = ConfigDict(extra="allow")

    node_id: str
    needs: list[str] = Field(default_factory=list)
    instruction_refs: list[str] = Field(default_factory=list)

    def apply(self, shared: GraphSharedState) -> NodePrivateContext:
        return project_node_context(
            shared,
            needs=self.needs,
            node_id=self.node_id,
            instruction_refs=self.instruction_refs,
        )
