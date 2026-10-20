"""CLI recipe adapters: recipe id → instrumentor execution (map multibind).

``GraphTemplate`` remains catalog membership. These adapters teach the CLI
instrumentor how to turn ``run_recipe`` YAML params into a run + observation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, cast

from mechaharness.cli_commands import RunRecipeCommand


class CliRecipeAdapter(ABC):
    """One catalog recipe the CLI ``run_recipe`` verb can execute."""

    name: ClassVar[str]

    @abstractmethod
    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        """Return a :class:`CliStepResult`."""


def _event_dict(event: Any) -> dict[str, Any]:
    data = cast(dict[str, Any], event.model_dump(mode="json"))
    ts = data.get("ts")
    if isinstance(ts, str):
        data["ts"] = ts.replace("+00:00", "Z") if ts.endswith("+00:00") else ts
    return data


class HarnessRunRecipeAdapter(CliRecipeAdapter):
    name = "harness_run"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.core.contract import RunRequest
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.recipe_runner import (
            instantiate_recipe,
            list_recipes,
            run_harness_recipe,
        )

        if not body.prompt:
            raise ValueError("run_recipe harness_run requires prompt=")
        before = len(runtime.event_log.query())
        catalog = {row["name"] for row in list_recipes()}
        response = await run_harness_recipe(
            RunRequest(
                prompt=body.prompt,
                backend=body.backend,
                family=body.family,
                model=body.model or runtime.model,
                max_turns=body.max_turns,
            ),
            tools=runtime.tools if len(runtime.tools) else None,
            event_log=runtime.event_log,
        )
        graph = instantiate_recipe(
            "harness_run",
            GraphTemplateParams(
                goal="harness_run",
                inputs={"prompt": body.prompt},
                soft_bindings={
                    "prompt": body.prompt,
                    "backend": body.backend,
                    "family": body.family,
                },
            ),
        )
        from mechaharness.cli_instrumentor import _token_totals
        from mechaharness.core.events import Event

        # Harness DI owns a separate EventLog; mirror records onto the CLI log
        # so script-level observation sees inference / cost / tokens.
        for raw in response.events or []:
            if isinstance(raw, dict):
                runtime.event_log.emit(Event.model_validate(raw))
            else:
                runtime.event_log.emit(raw)
        after_events = runtime.event_log.query()[before:]
        event_dicts = [_event_dict(e) for e in after_events]
        units = sum(
            float(e.payload.get("units") or 0)
            for e in after_events
            if e.type == "core:cost"
        )
        prompt, completion, total = _token_totals(event_dicts)
        return CliStepResult(
            verb="run_recipe",
            text=response.final_text,
            status="ok",
            event_types=[e.type for e in after_events],
            events=event_dicts,
            cost_units=units,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            clock_iso=runtime.datetime_service.now_utc_iso(),
            turns=int(response.turns or 0),
            recipe_in_catalog="harness_run" in catalog,
            subgraph_node_ids=list(graph.nodes),
        )


class BackendDescribeRecipeAdapter(CliRecipeAdapter):
    name = "backend_describe"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.config import Settings
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.recipe_runner import (
            instantiate_recipe,
            list_recipes,
            run_backend_describe_recipe,
        )

        catalog = {row["name"] for row in list_recipes()}
        settings = Settings(
            inference_backend=body.backend,
            model=body.model or runtime.model,
        )
        description = await run_backend_describe_recipe(settings)
        graph = instantiate_recipe(
            "backend_describe",
            GraphTemplateParams(
                goal="backend_describe",
                soft_bindings={"backend": body.backend},
            ),
        )
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status="ok",
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="backend_describe" in catalog,
            description_name=str(description.get("name") or ""),
            subgraph_node_ids=list(graph.nodes),
        )


class ConversationalToolLoopRecipeAdapter(CliRecipeAdapter):
    name = "conversational_tool_loop"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        import json
        from collections.abc import Mapping

        from mechaharness.budget import BudgetPolicy
        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.conversational_tool_loop_runner import (
            ConversationalToolLoopRunner,
        )
        from mechaharness.core.types import ChatMessage, CompletionRequest, Role
        from mechaharness.graph import ExecutionGraph
        from mechaharness.graph_templates import (
            ConversationalToolLoopTemplate,
            GraphTemplateParams,
        )
        from mechaharness.host_kit import host_graph_executor
        from mechaharness.tools.base import Tool, ToolRegistry

        before = len(runtime.event_log.query())
        tools = ToolRegistry()
        for definition in runtime.tools.definitions():
            tools.register(runtime.tools.get(definition.name))
        if body.tool_name not in tools:
            tools.register(
                Tool(body.tool_name, lambda: "ok", description="cli tool")
            )

        async def complete(
            messages: list[dict[str, Any]],
            meta: Mapping[str, Any],
        ) -> dict[str, Any]:
            del messages
            from mechaharness.core.events import Event, Inference, event_type_key
            from mechaharness.core.types import Usage

            response = await runtime.completer.complete(
                CompletionRequest(
                    model=runtime.model,
                    messages=[ChatMessage(role=Role.USER, content="continue")],
                )
            )
            message = response.message
            round_i = int(meta.get("round") or 0)
            runtime.event_log.emit(
                Event(
                    type=event_type_key(Inference),
                    agent_id=runtime.agent_id,
                    run_id="cli:conversational_tool_loop",
                    payload={
                        "completer": type(runtime.completer).__name__,
                        "model": runtime.model,
                        "finish_reason": response.finish_reason,
                        "content": message.content,
                        "parent_node_id": "tools",
                        "component_id": f"tools/inference:{round_i + 1}",
                        "execution_node_id": "tools",
                        "usage": Usage.for_event(response.usage),
                    },
                )
            )
            out: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or "",
            }
            if message.tool_calls:
                out["tool_calls"] = [
                    {
                        "id": call.id,
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in message.tool_calls
                ]
            return out

        def dispatch_tool(name: str, args: Any) -> str:
            del args
            return f"ok:{name}"

        runner = ConversationalToolLoopRunner(
            complete=complete,
            dispatch_tool=dispatch_tool,
        )
        graph = ConversationalToolLoopTemplate().instantiate(
            GraphTemplateParams(
                goal="loop",
                inputs={"max_iterations": body.max_iterations},
            )
        )
        executor = host_graph_executor(
            runners=[runner],
            event_log=runtime.event_log,
            agent_id=runtime.agent_id,
        )
        result = await executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            run_id="cli:conversational_tool_loop",
            skip_linkage=True,
        )
        tools_node = result.graph.nodes["tools"]
        child = ExecutionGraph.resume(tools_node.subgraph or {})
        node_ids = list(child.nodes)
        after_events = runtime.event_log.query()[before:]
        event_dicts = [_event_dict(e) for e in after_events]
        priced = sum(
            float(e.payload.get("units") or 0)
            for e in after_events
            if e.type == "core:cost"
        )
        # Graph node charges (rounds) plus any priced inference units.
        units = max(float(result.budget_spent), float(priced))
        from mechaharness.cli_instrumentor import _token_totals

        prompt, completion, total = _token_totals(event_dicts)
        return CliStepResult(
            verb="run_recipe",
            text=str(tools_node.payload.get("final_text") or "") or None,
            status=result.status,
            event_types=[e.type for e in after_events],
            events=event_dicts,
            cost_units=units,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            clock_iso=runtime.datetime_service.now_utc_iso(),
            rounds=int(tools_node.payload.get("rounds") or 0),
            subgraph_node_ids=node_ids,
            fields={"budget_spent": float(result.budget_spent)},
        )


def default_cli_recipe_adapter_classes() -> dict[str, type[CliRecipeAdapter]]:
    return {
        HarnessRunRecipeAdapter.name: HarnessRunRecipeAdapter,
        BackendDescribeRecipeAdapter.name: BackendDescribeRecipeAdapter,
        ConversationalToolLoopRecipeAdapter.name: ConversationalToolLoopRecipeAdapter,
    }


class _CliRecipeAdapterMapHost:
    def __init__(self, adapters: dict[str, CliRecipeAdapter]) -> None:
        self.adapters = adapters


def resolve_cli_recipe_adapters(config: Any) -> dict[str, CliRecipeAdapter]:
    from mechaharness.di import _expose_ctor_type_hints, get_injector

    _expose_ctor_type_hints(_CliRecipeAdapterMapHost)
    return cast(
        dict[str, CliRecipeAdapter],
        get_injector(config).inject(_CliRecipeAdapterMapHost).adapters,
    )


__all__ = [
    "BackendDescribeRecipeAdapter",
    "CliRecipeAdapter",
    "ConversationalToolLoopRecipeAdapter",
    "HarnessRunRecipeAdapter",
    "default_cli_recipe_adapter_classes",
    "resolve_cli_recipe_adapters",
]
