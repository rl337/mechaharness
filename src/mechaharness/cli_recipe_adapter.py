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


class ContextPackRecipeAdapter(CliRecipeAdapter):
    """Execute ``context_pack``: RagRetriever → assemble_context_within_budget."""

    name = "context_pack"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from pathlib import Path

        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.context_pack_runner import RagPackRunner, RagRetrieveRunner
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.rag import RagRetriever, UnboundRagRetriever
        from mechaharness.recipe_bind import RecipeBind
        from mechaharness.recipe_runner import instantiate_recipe, list_recipes, run_recipe

        catalog = {row["name"] for row in list_recipes()}
        soft: dict[str, Any] = dict(body.soft_bindings or {})
        goal = "context_pack"
        if body.path:
            base = getattr(runtime, "bind_base_dir", None)
            path = Path(body.path)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            bind = RecipeBind.from_path(path)
            soft = {**bind.soft_bindings, **soft}
            goal = bind.goal or bind.name or goal
        if "query" not in soft:
            soft["query"] = body.prompt or "context"
        params = GraphTemplateParams(goal=goal, soft_bindings=soft)
        retriever = getattr(runtime, "rag_retriever", None)
        if retriever is None:
            retriever = UnboundRagRetriever()
        assert isinstance(retriever, RagRetriever)
        before = len(runtime.event_log.query())
        result = await run_recipe(
            "context_pack",
            params=params,
            runners=[
                RagRetrieveRunner(retriever),
                RagPackRunner(),
            ],
            event_log=runtime.event_log,
            run_id="cli:context_pack",
        )
        pack = result.graph.nodes.get("pack")
        payload = dict(pack.payload) if pack is not None else {}
        after_events = runtime.event_log.query()[before:]
        graph = instantiate_recipe("context_pack", params)
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status=result.status,
            event_types=[e.type for e in after_events],
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="context_pack" in catalog,
            subgraph_node_ids=list(graph.nodes),
            cost_units=float(result.budget_spent),
            fields={
                "selected_ids": list(payload.get("selected_ids") or []),
                "token_total": int(payload.get("token_total") or 0),
                "within_budget": bool(payload.get("within_budget")),
                "candidate_count": int(payload.get("candidate_count") or 0),
                "budget_spent": float(result.budget_spent),
            },
        )


class DecisionPlaneRecipeAdapter(CliRecipeAdapter):
    """Execute ``decision_plane``: project → ask → policy → escalate (+ shadow)."""

    name = "decision_plane"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from pathlib import Path

        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.decision_plane_runner import (
            decision_plane_runners,
            telemetry_fields_from_graph,
        )
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.recipe_bind import RecipeBind
        from mechaharness.recipe_runner import instantiate_recipe, list_recipes, run_recipe

        catalog = {row["name"] for row in list_recipes()}
        soft: dict[str, Any] = dict(body.soft_bindings or {})
        inputs: dict[str, Any] = {}
        goal = "decision_plane"
        if body.path:
            base = getattr(runtime, "bind_base_dir", None)
            path = Path(body.path)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            bind = RecipeBind.from_path(path)
            soft = {**bind.soft_bindings, **soft}
            inputs = dict(bind.inputs)
            goal = bind.goal or bind.name or goal
        params = GraphTemplateParams(
            goal=goal,
            soft_bindings=soft,
            inputs=inputs,
        )
        before = len(runtime.event_log.query())
        result = await run_recipe(
            "decision_plane",
            params=params,
            runners=decision_plane_runners(),
            event_log=runtime.event_log,
            run_id="cli:decision_plane",
        )
        after_events = runtime.event_log.query()[before:]
        nodes = result.graph.nodes
        project = nodes.get("project_state")
        policy = nodes.get("apply_policy")
        escalate = nodes.get("escalate")
        shadow = nodes.get("shadow_ask")
        ask = nodes.get("ask_batch")
        project_payload = dict(project.payload) if project is not None else {}
        policy_payload = dict(policy.payload) if policy is not None else {}
        escalate_payload = dict(escalate.payload) if escalate is not None else {}
        shadow_payload = dict(shadow.payload) if shadow is not None else {}
        ask_payload = dict(ask.payload) if ask is not None else {}

        production_action = policy_payload.get("final_action")
        shadow_action = shadow_payload.get("final_action")
        agreement = None
        if shadow is not None:
            agreement = production_action == shadow_action and (
                bool(policy_payload.get("escalate"))
                == bool(shadow_payload.get("escalate"))
            )

        model_ref = inputs.get("model_ref") or ask_payload.get("model_ref")
        latency_ms = inputs.get("latency_ms")
        if latency_ms is not None:
            latency_ms = float(latency_ms)
        tel = telemetry_fields_from_graph(
            graph_nodes=nodes,
            model_ref=str(model_ref) if model_ref is not None else None,
            latency_ms=latency_ms,
            raw_body=inputs.get("raw_body"),
        )
        final_action = policy_payload.get("final_action")
        if inputs.get("final_action") and not policy_payload.get("escalate"):
            final_action = inputs["final_action"]
            tel["final_action"] = final_action

        shape = instantiate_recipe("decision_plane", params)
        from mechaharness.recipe_runner import describe_recipe

        describe = describe_recipe("decision_plane")
        soft_point_names = {
            str(p.get("name")) for p in (describe.get("soft_points") or []) if p.get("name")
        }
        fields: dict[str, Any] = {
            "template_name": "decision_plane",
            "has_soft_point": bool(soft_point_names),
            "soft_point_decision_model": "decision_model" in soft_point_names,
            "describe_has_param_count": "param_count" in describe,
            "projection": project_payload.get("projection"),
            "facts": project_payload.get("facts_keys")
            or list(_mapping_keys(project_payload.get("facts"))),
            "projection_has_secret": bool(project_payload.get("projection_has_secret")),
            "no_model_invocation": bool(project_payload.get("no_model_invocation", True)),
            "facts_fingerprint_nonempty": bool(
                project_payload.get("facts_fingerprint_nonempty")
            ),
            "final_action": final_action,
            "escalate": bool(
                escalate_payload.get("escalate", policy_payload.get("escalate"))
            ),
            "escalation_reason": escalate_payload.get("escalation_reason")
            or policy_payload.get("escalation_reason"),
            "escalation_route": escalate_payload.get("escalation_route")
            or policy_payload.get("escalation_route"),
            "batch_invocation_count": int(
                ask_payload.get("batch_invocation_count")
                or policy_payload.get("batch_invocation_count")
                or 0
            ),
            "production_action": production_action,
            "shadow_controls_execution": False,
            "both_outcomes_recorded": shadow is not None and policy is not None,
            "agreement": agreement,
            "ask_model_ref": ask_payload.get("model_ref"),
            "budget_spent": float(result.budget_spent),
            **tel,
        }

        return CliStepResult(
            verb="run_recipe",
            text=None,
            status=result.status,
            event_types=[e.type for e in after_events],
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="decision_plane" in catalog,
            subgraph_node_ids=list(shape.nodes),
            cost_units=float(result.budget_spent),
            fields=fields,
        )


def _mapping_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return list(value.keys())
    return []


def default_cli_recipe_adapter_classes() -> dict[str, type[CliRecipeAdapter]]:
    return {
        HarnessRunRecipeAdapter.name: HarnessRunRecipeAdapter,
        BackendDescribeRecipeAdapter.name: BackendDescribeRecipeAdapter,
        ConversationalToolLoopRecipeAdapter.name: ConversationalToolLoopRecipeAdapter,
        ContextPackRecipeAdapter.name: ContextPackRecipeAdapter,
        DecisionPlaneRecipeAdapter.name: DecisionPlaneRecipeAdapter,
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
    "ContextPackRecipeAdapter",
    "ConversationalToolLoopRecipeAdapter",
    "HarnessRunRecipeAdapter",
    "default_cli_recipe_adapter_classes",
    "resolve_cli_recipe_adapters",
]
