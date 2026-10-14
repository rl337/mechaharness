"""Backend-describe Agentic Recipe — CLI ``describe`` as a graph node."""

from __future__ import annotations

from mechaharness.graph import ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)


class BackendDescribeTemplate(GraphTemplate):
    """Instantiate an inference Strategy and return ``describe()`` metadata.

    Single ``describe`` node. Soft-bind ``backend`` (required) plus optional
    model / base_url / api_key. Library default runners power CLI ``describe``.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     BackendDescribeTemplate, GraphTemplateParams,
        ... )
        >>> graph = BackendDescribeTemplate().instantiate(GraphTemplateParams(
        ...     soft_bindings={"backend": "mock"},
        ... ))
        >>> graph.template_name
        'backend_describe'
        >>> list(graph.nodes)
        ['describe']
    """

    name = "backend_describe"
    version = "1"
    summary = (
        "Describe a configured inference backend (name, base_url, model, auth). "
        "Library stand-in for the classic CLI describe path."
    )
    soft_points = (
        SoftPoint(
            name="describe_kind",
            kind="runner_kind",
            description="Node kind for describe",
            default="backend_describe",
        ),
        SoftPoint(
            name="backend",
            kind="provider",
            description="Inference backend name",
            required=True,
        ),
        SoftPoint(
            name="model",
            kind="model",
            description="Model id override",
            required=False,
        ),
        SoftPoint(
            name="base_url",
            kind="provider",
            description="Endpoint override",
            required=False,
        ),
        SoftPoint(
            name="api_key",
            kind="provider",
            description="API key override",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = params.inputs
        backend = bindings.get("backend", inputs.get("backend"))
        if not backend:
            raise ValueError("backend_describe requires soft_bindings/inputs backend")
        kind = str(bindings.get("describe_kind", "backend_describe"))
        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        graph.add_node(
            make_node(
                id="describe",
                kind=kind,
                goal=f"describe backend {backend}",
                payload={
                    "phase": "describe",
                    "backend": backend,
                    "model": bindings.get("model", inputs.get("model")),
                    "base_url": bindings.get("base_url", inputs.get("base_url")),
                    "api_key": bindings.get("api_key", inputs.get("api_key")),
                },
            )
        )
        return graph
