"""Discover and execute Agentic Recipes via GraphTemplate + GraphExecutor.

This is **not** a second runtime. Instantiation still yields an ordinary
:class:`~mechaharness.graph.ExecutionGraph`; execution uses
:func:`~mechaharness.host_kit.host_graph_executor` /
:class:`~mechaharness.graph_executor.GraphExecutor`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.budget import BudgetPolicy
from mechaharness.config import Settings
from mechaharness.core.contract import RunRequest, RunResponse
from mechaharness.core.events import EventLog
from mechaharness.di import build_injector
from mechaharness.factory import settings_from_request
from mechaharness.graph_executor import GraphExecutor, GraphNodeRunner, GraphResult
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    GraphTemplateRegistry,
)
from mechaharness.graph_templates.catalog import default_graph_templates
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness_run_runner import (
    BackendDescribeRunner,
    HarnessLoopRunner,
    HarnessPrepareRunner,
    HarnessRenderRunner,
)
from mechaharness.host_kit import host_graph_executor
from mechaharness.inference.base import InferenceStrategy
from mechaharness.tools.base import ToolRegistry


def resolve_registry(
    registry: GraphTemplateRegistry | None = None,
) -> GraphTemplateRegistry:
    """Return ``registry`` or the library default catalog."""
    return registry if registry is not None else default_graph_templates()


def list_recipes(
    registry: GraphTemplateRegistry | None = None,
    *,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """Catalog entries for discovery (CLI ``recipes`` / host UIs)."""
    reg = resolve_registry(registry)
    names = reg.active_names() if active_only else reg.names()
    out: list[dict[str, Any]] = []
    for name in names:
        template = reg.get(name)
        if template is not None:
            out.append(template.describe())
    return out


def describe_recipe(
    name: str,
    registry: GraphTemplateRegistry | None = None,
) -> dict[str, Any]:
    """Metadata for one recipe (soft points, summary, status)."""
    template = get_recipe(name, registry=registry)
    return template.describe()


def get_recipe(
    name: str,
    registry: GraphTemplateRegistry | None = None,
) -> GraphTemplate:
    """Lookup a catalog entry or raise ``KeyError``."""
    reg = resolve_registry(registry)
    template = reg.get(name)
    if template is None:
        known = ", ".join(reg.names()) or "(empty)"
        raise KeyError(f"unknown recipe {name!r}; known: {known}")
    return template


def instantiate_recipe(
    name: str,
    params: GraphTemplateParams | None = None,
    *,
    registry: GraphTemplateRegistry | None = None,
):
    """Expand a recipe into an :class:`~mechaharness.graph.ExecutionGraph`."""
    template = get_recipe(name, registry=registry)
    return template.instantiate(params or GraphTemplateParams())


def default_recipe_runners(
    *,
    harness: AbstractHarness | None = None,
) -> list[GraphNodeRunner]:
    """Library runners for CLI recipes (``harness_run``, ``backend_describe``)."""
    return [
        HarnessPrepareRunner(),
        HarnessLoopRunner(harness=harness),
        HarnessRenderRunner(),
        BackendDescribeRunner(),
    ]


async def run_recipe(
    name: str,
    *,
    params: GraphTemplateParams | None = None,
    runners: Sequence[GraphNodeRunner] | None = None,
    registry: GraphTemplateRegistry | None = None,
    budget_policy: BudgetPolicy | None = None,
    event_log: EventLog | None = None,
    run_id: str | None = None,
    skip_linkage: bool = True,
    executor: GraphExecutor | None = None,
) -> GraphResult:
    """Instantiate ``name`` and execute with GraphExecutor (composition helper)."""
    graph = instantiate_recipe(name, params, registry=registry)
    if executor is None:
        if runners is None:
            raise ValueError("run_recipe requires runners= or executor=")
        executor = host_graph_executor(runners=runners, event_log=event_log)
    return await executor.run(
        graph,
        budget_policy=budget_policy or BudgetPolicy.unlimited(),
        run_id=run_id or f"recipe:{name}",
        skip_linkage=skip_linkage,
    )


def _bindings_from_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None}


async def run_harness_recipe(
    request: RunRequest,
    *,
    tools: ToolRegistry | None = None,
    registry: GraphTemplateRegistry | None = None,
    event_log: EventLog | None = None,
) -> RunResponse:
    """Execute catalog id ``harness_run`` for a classic RunRequest.

    Builds Settings + harness via DI, binds :class:`HarnessLoopRunner`, then
    walks the prepare → harness_loop → render graph.
    """
    settings = settings_from_request(request)
    injector = build_injector(settings, tools=tools)
    inference: InferenceStrategy = injector.inject(InferenceStrategy)
    try:
        harness: AbstractHarness = injector.inject(AbstractHarness)
        soft = _bindings_from_mapping(
            {
                "prompt": request.prompt,
                "backend": request.backend or settings.inference_backend,
                "family": request.family or settings.harness_family,
                "model": request.model or settings.model,
                "system_prompt": request.system_prompt
                if request.system_prompt is not None
                else settings.system_prompt,
                "max_turns": request.max_turns,
                "api_key": request.api_key
                if request.api_key is not None
                else settings.api_key,
                "base_url": request.base_url
                if request.base_url is not None
                else settings.base_url,
                "temperature": request.temperature
                if request.temperature is not None
                else settings.temperature,
            }
        )
        params = GraphTemplateParams(
            goal="harness_run",
            inputs={"prompt": request.prompt},
            soft_bindings=soft,
        )
        result = await run_recipe(
            "harness_run",
            params=params,
            runners=default_recipe_runners(harness=harness),
            registry=registry,
            event_log=event_log,
            run_id="cli:harness_run",
        )
        if result.status != "ok":
            raise RuntimeError(
                result.error or f"harness_run failed with status={result.status}"
            )
        render = result.graph.nodes.get("render")
        payload = dict(render.payload) if render is not None else {}
        return RunResponse(
            final_text=payload.get("final_text"),
            turns=int(payload.get("turns") or 0),
            messages=list(payload.get("messages") or []),
            events=list(payload.get("events") or []),
        )
    finally:
        await inference.aclose()


async def run_backend_describe_recipe(
    settings: Settings,
    *,
    registry: GraphTemplateRegistry | None = None,
) -> dict[str, Any]:
    """Execute catalog id ``backend_describe`` for CLI ``describe``."""
    params = GraphTemplateParams(
        goal="backend_describe",
        soft_bindings=_bindings_from_mapping(
            {
                "backend": settings.inference_backend,
                "model": settings.model,
                "base_url": settings.base_url,
                "api_key": settings.api_key,
            }
        ),
    )
    result = await run_recipe(
        "backend_describe",
        params=params,
        runners=default_recipe_runners(),
        registry=registry,
        run_id="cli:backend_describe",
    )
    if result.status != "ok":
        raise RuntimeError(
            result.error or f"backend_describe failed with status={result.status}"
        )
    node = result.graph.nodes.get("describe")
    if node is None:
        raise RuntimeError("backend_describe graph missing describe node")
    description = node.payload.get("description")
    if not isinstance(description, dict):
        raise RuntimeError("backend_describe did not produce description payload")
    return description


__all__ = [
    "default_recipe_runners",
    "describe_recipe",
    "get_recipe",
    "instantiate_recipe",
    "list_recipes",
    "resolve_registry",
    "run_backend_describe_recipe",
    "run_harness_recipe",
    "run_recipe",
]
