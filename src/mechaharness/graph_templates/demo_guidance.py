"""Demo recipe that requests external artistic guidance (generator IoC trial).

Catalog id: ``demo_guidance``. Soft point kind ``guidance`` projects a
``guidance_request`` node component. Prefer driving via
``DurableGraphGenerator`` / MCP ``generator_start`` rather than one-shot
``GraphExecutor.run``.
"""

from __future__ import annotations

from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
)
from mechaharness.isolation.isolation_contract import TemplateIOContract


class DemoGuidanceTemplate(GraphTemplate):
    """Minimal recipe whose soft point asks a frontier driver for direction."""

    name = "demo_guidance"
    version = "1"
    category = "agentic_recipe"
    description = (
        "Demo: local prep node then external guidance soft point for artistic "
        "direction — drive with DurableGraphGenerator / MCP."
    )
    soft_points = (
        SoftPoint(
            name="external_guidance",
            kind="guidance",
            description=(
                "How should exhaustion affect the sword maneuver in this shot?"
            ),
            required=True,
            default={
                "choices": [
                    {"id": "slow", "label": "Slower, imperfect technique"},
                    {
                        "id": "precise",
                        "label": "Precise maneuver followed by collapse",
                    },
                ],
                "recommendation": "precise",
                "requested_authority": "artistic_direction",
                "evidence_refs": ["artifact://demo/performance-analysis"],
            },
        ),
    )
    io_contract = TemplateIOContract(
        inputs={"scene_brief": "string"},
        outputs={"direction": "string"},
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        graph = ExecutionGraph(
            goal=params.goal or "demo artistic direction",
            template_name=self.name,
            template_version=self.version,
        )
        graph.add_node(
            GraphNode(
                id="prepare",
                kind="prepare_analysis",
                goal="Local performance analysis",
                payload={
                    "scene_brief": (params.inputs or {}).get("scene_brief", ""),
                    "soft_points": ["external_guidance"],
                },
            )
        )
        graph.add_node(
            GraphNode(
                id="apply_direction",
                kind="apply_direction",
                goal="Apply driver guidance",
                depends_on=["prepare"],
                payload={"soft_points": ["external_guidance"]},
            )
        )
        return graph
