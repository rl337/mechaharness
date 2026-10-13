"""Harness-run Agentic Recipe — CLI ``run`` as a readable graph.

``prepare`` → ``harness_loop`` → ``render`` mirrors a single prompt through the
configured inference Strategy + harness family, with interiors visible as
node components (inference / tool_call / turn_start) under ``harness_loop``.
"""

from __future__ import annotations

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)


class HarnessRunTemplate(GraphTemplate):
    """Single-prompt harness run as an ordinary ExecutionGraph.

    Nodes: ``prepare`` → ``harness_loop`` → ``render``. Soft-bind backend,
    family, model, system prompt, and max turns (or pass via ``inputs``).
    Library default runners execute this from the CLI ``run`` path.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, HarnessRunTemplate,
        ... )
        >>> graph = HarnessRunTemplate().instantiate(GraphTemplateParams(
        ...     goal="cli run",
        ...     soft_bindings={"prompt": "hello", "family": "pass_through"},
        ... ))
        >>> graph.template_name
        'harness_run'
        >>> sorted(graph.nodes)
        ['harness_loop', 'prepare', 'render']
    """

    name = "harness_run"
    version = "1"
    summary = (
        "Prepare prompt context → run harness family loop → render final text. "
        "Library stand-in for the classic CLI/HTTP run path."
    )
    soft_points = (
        SoftPoint(
            name="prepare_kind",
            kind="runner_kind",
            description="Node kind for prepare / bind settings",
            default="harness_prepare",
        ),
        SoftPoint(
            name="harness_loop_kind",
            kind="runner_kind",
            description="Node kind for the harness family loop",
            default="harness_loop",
        ),
        SoftPoint(
            name="render_kind",
            kind="runner_kind",
            description="Node kind for packing final text / events",
            default="harness_render",
        ),
        SoftPoint(
            name="backend",
            kind="provider",
            description="Inference backend name (Settings.inference_backend)",
            required=False,
        ),
        SoftPoint(
            name="family",
            kind="policy",
            description="Harness family name (Settings.harness_family)",
            required=False,
        ),
        SoftPoint(
            name="model",
            kind="model",
            description="Model id",
            required=False,
        ),
        SoftPoint(
            name="system_prompt",
            kind="prompt",
            description="System prompt override",
            required=False,
        ),
        SoftPoint(
            name="max_turns",
            kind="budget",
            description="Harness max turns",
            default=8,
        ),
        SoftPoint(
            name="prompt",
            kind="task_state",
            description="User prompt text (also accepted via inputs['prompt'])",
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = params.inputs
        prompt = str(bindings.get("prompt", inputs.get("prompt", "")))
        prepare_kind = str(bindings.get("prepare_kind", "harness_prepare"))
        loop_kind = str(bindings.get("harness_loop_kind", "harness_loop"))
        render_kind = str(bindings.get("render_kind", "harness_render"))
        shared = {
            "prompt": prompt,
            "backend": bindings.get("backend", inputs.get("backend")),
            "family": bindings.get("family", inputs.get("family")),
            "model": bindings.get("model", inputs.get("model")),
            "system_prompt": bindings.get("system_prompt", inputs.get("system_prompt")),
            "max_turns": int(bindings.get("max_turns", inputs.get("max_turns", 8))),
            "api_key": bindings.get("api_key", inputs.get("api_key")),
            "base_url": bindings.get("base_url", inputs.get("base_url")),
            "temperature": bindings.get("temperature", inputs.get("temperature")),
        }
        graph = ExecutionGraph(goal=params.goal or self.name, version=self.version)
        prepare = make_node(
            id="prepare",
            kind=prepare_kind,
            goal="bind run settings and prompt",
            payload={"phase": "prepare", **shared},
        )
        loop = make_node(
            id="harness_loop",
            kind=loop_kind,
            goal="run harness family loop",
            depends_on=[prepare.id],
            payload={"phase": "harness_loop", **shared},
        )
        render = make_node(
            id="render",
            kind=render_kind,
            goal="pack final text and transcript",
            depends_on=[loop.id],
            payload={"phase": "render"},
        )
        for node in (prepare, loop, render):
            graph.add_node(node)
        graph.add_dependency(
            DependencyEdge(
                from_node=prepare.id,
                to_node=loop.id,
                types=["data"],
                reason="settings_and_prompt",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node=loop.id,
                to_node=render.id,
                types=["data"],
                reason="harness_result",
            )
        )
        return graph
