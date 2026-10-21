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


class VerifyRepairRecipeAdapter(CliRecipeAdapter):
    """Execute ``verify_repair``: produce → verify → repair → complete."""

    name = "verify_repair"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from pathlib import Path

        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.recipe_bind import RecipeBind, observe_instantiated_recipe
        from mechaharness.recipe_runner import get_recipe, list_recipes, run_recipe
        from mechaharness.verify_repair_runner import verify_repair_runners

        catalog = {row["name"] for row in list_recipes()}
        soft: dict[str, Any] = dict(body.soft_bindings or {})
        inputs: dict[str, Any] = {}
        acceptance: list[Any] = []
        goal = "verify_repair"
        bind: RecipeBind | None = None
        if body.path:
            base = getattr(runtime, "bind_base_dir", None)
            path = Path(body.path)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            bind = RecipeBind.from_path(path)
            soft = {**bind.soft_bindings, **soft}
            inputs = dict(bind.inputs)
            acceptance = list(bind.acceptance)
            goal = bind.goal or bind.name or goal
        params = GraphTemplateParams(
            goal=goal,
            soft_bindings=soft,
            inputs=inputs,
            acceptance=acceptance,
            stop_contract=bind.stop_contract if bind is not None else None,
        )
        before = len(runtime.event_log.query())
        result = await run_recipe(
            "verify_repair",
            params=params,
            runners=verify_repair_runners(),
            event_log=runtime.event_log,
            run_id="cli:verify_repair",
        )
        after_events = runtime.event_log.query()[before:]
        complete = result.graph.nodes.get("complete")
        repair = result.graph.nodes.get("repair")
        verify = result.graph.nodes.get("verify")
        complete_payload = dict(complete.payload) if complete else {}
        repair_payload = dict(repair.payload) if repair else {}
        verify_payload = dict(verify.payload) if verify else {}
        shape_fields: dict[str, Any] = {}
        if bind is not None:
            template = get_recipe("verify_repair")
            observed = observe_instantiated_recipe(
                bind, result.graph, template
            )
            shape_fields = dict(observed["fields"])
        fields = {
            **shape_fields,
            "template_name": "verify_repair",
            "verification_passed": bool(
                complete_payload.get("verification_passed")
                or repair_payload.get("verification_passed")
                or verify_payload.get("verification_passed")
            ),
            "repair_attempts": int(
                complete_payload.get("repair_attempts")
                or repair_payload.get("repair_attempts")
                or 0
            ),
            "final_status": complete_payload.get("final_status") or result.status,
            "budget_spent": float(result.budget_spent),
        }
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status=result.status,
            event_types=[e.type for e in after_events],
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="verify_repair" in catalog,
            subgraph_node_ids=list(result.graph.nodes),
            cost_units=float(result.budget_spent),
            fields=fields,
        )


class BoundedRetryRecipeAdapter(CliRecipeAdapter):
    """Execute ``bounded_retry``: attempt → classify → permit → backoff/escalate."""

    name = "bounded_retry"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from pathlib import Path

        from mechaharness.bounded_retry_runner import bounded_retry_runners
        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.recipe_bind import RecipeBind, observe_instantiated_recipe
        from mechaharness.recipe_runner import get_recipe, list_recipes, run_recipe

        catalog = {row["name"] for row in list_recipes()}
        soft: dict[str, Any] = dict(body.soft_bindings or {})
        inputs: dict[str, Any] = {}
        goal = "bounded_retry"
        bind: RecipeBind | None = None
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
            stop_contract=bind.stop_contract if bind is not None else None,
        )
        before = len(runtime.event_log.query())
        result = await run_recipe(
            "bounded_retry",
            params=params,
            runners=bounded_retry_runners(),
            event_log=runtime.event_log,
            run_id="cli:bounded_retry",
        )
        after_events = runtime.event_log.query()[before:]
        attempt = result.graph.nodes.get("attempt")
        permit = result.graph.nodes.get("permit_retry")
        escalate = result.graph.nodes.get("escalate")
        backoff = result.graph.nodes.get("backoff")
        shape_fields: dict[str, Any] = {}
        if bind is not None:
            template = get_recipe("bounded_retry")
            observed = observe_instantiated_recipe(bind, result.graph, template)
            shape_fields = dict(observed["fields"])
        fields = {
            **shape_fields,
            "template_name": "bounded_retry",
            "attempt_count": int(
                (attempt.payload.get("attempt_count") if attempt else None)
                or (permit.payload.get("attempt_count") if permit else None)
                or 0
            ),
            "attempt_succeeded": bool(
                (attempt.payload.get("attempt_succeeded") if attempt else False)
                or (permit.payload.get("attempt_succeeded") if permit else False)
            ),
            "retry_permitted": bool(
                permit.payload.get("retry_permitted") if permit else False
            ),
            "escalated": bool(escalate.payload.get("escalated") if escalate else False),
            "backoff_applied": bool(
                backoff.payload.get("backoff_applied") if backoff else False
            ),
            "budget_spent": float(result.budget_spent),
        }
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status=result.status,
            event_types=[e.type for e in after_events],
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="bounded_retry" in catalog,
            subgraph_node_ids=list(result.graph.nodes),
            cost_units=float(result.budget_spent),
            fields=fields,
        )


class IndependentReviewRecipeAdapter(CliRecipeAdapter):
    """Execute ``independent_review``: produce → isolated reviews → aggregate."""

    name = "independent_review"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from pathlib import Path

        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.independent_review_runner import independent_review_runners
        from mechaharness.recipe_bind import RecipeBind, observe_instantiated_recipe
        from mechaharness.recipe_runner import get_recipe, list_recipes, run_recipe

        catalog = {row["name"] for row in list_recipes()}
        soft: dict[str, Any] = dict(body.soft_bindings or {})
        inputs: dict[str, Any] = {}
        acceptance: list[Any] = []
        goal = "independent_review"
        bind: RecipeBind | None = None
        if body.path:
            base = getattr(runtime, "bind_base_dir", None)
            path = Path(body.path)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            bind = RecipeBind.from_path(path)
            soft = {**bind.soft_bindings, **soft}
            inputs = dict(bind.inputs)
            acceptance = list(bind.acceptance)
            goal = bind.goal or bind.name or goal
        params = GraphTemplateParams(
            goal=goal,
            soft_bindings=soft,
            inputs=inputs,
            acceptance=acceptance,
        )
        before = len(runtime.event_log.query())
        result = await run_recipe(
            "independent_review",
            params=params,
            runners=independent_review_runners(),
            event_log=runtime.event_log,
            run_id="cli:independent_review",
        )
        after_events = runtime.event_log.query()[before:]
        aggregate = result.graph.nodes.get("aggregate_reviews")
        agg_payload = dict(aggregate.payload) if aggregate else {}
        shape_fields: dict[str, Any] = {}
        if bind is not None:
            template = get_recipe("independent_review")
            observed = observe_instantiated_recipe(bind, result.graph, template)
            shape_fields = dict(observed["fields"])
        fields = {
            **shape_fields,
            "template_name": "independent_review",
            "review_count": int(
                agg_payload.get("review_count")
                or shape_fields.get("review_count")
                or 0
            ),
            "omit_producer_reasoning": bool(
                agg_payload.get("omit_producer_reasoning")
                if "omit_producer_reasoning" in agg_payload
                else shape_fields.get("omit_producer_reasoning", True)
            ),
            "retain_disagreement": bool(
                agg_payload.get("retain_disagreement")
                if "retain_disagreement" in agg_payload
                else shape_fields.get("retain_disagreement", True)
            ),
            "disagreement_retained": bool(agg_payload.get("disagreement_retained")),
            "finding_count": int(agg_payload.get("finding_count") or 0),
            "findings": list(agg_payload.get("findings") or []),
            "budget_spent": float(result.budget_spent),
        }
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status=result.status,
            event_types=[e.type for e in after_events],
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="independent_review" in catalog,
            subgraph_node_ids=list(result.graph.nodes),
            cost_units=float(result.budget_spent),
            fields=fields,
        )


class EnvironmentRepairRecipeAdapter(CliRecipeAdapter):
    """Execute ``environment_repair``: diagnose → repair → recheck."""

    name = "environment_repair"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from pathlib import Path

        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.environment_repair_runner import environment_repair_runners
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.recipe_bind import RecipeBind, observe_instantiated_recipe
        from mechaharness.recipe_runner import get_recipe, list_recipes, run_recipe

        catalog = {row["name"] for row in list_recipes()}
        soft: dict[str, Any] = dict(body.soft_bindings or {})
        inputs: dict[str, Any] = {}
        acceptance: list[Any] = []
        goal = "environment_repair"
        bind: RecipeBind | None = None
        if body.path:
            base = getattr(runtime, "bind_base_dir", None)
            path = Path(body.path)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            bind = RecipeBind.from_path(path)
            soft = {**bind.soft_bindings, **soft}
            inputs = dict(bind.inputs)
            acceptance = list(bind.acceptance)
            goal = bind.goal or bind.name or goal
        params = GraphTemplateParams(
            goal=goal,
            soft_bindings=soft,
            inputs=inputs,
            acceptance=acceptance,
            stop_contract=bind.stop_contract if bind is not None else None,
        )
        before = len(runtime.event_log.query())
        result = await run_recipe(
            "environment_repair",
            params=params,
            runners=environment_repair_runners(),
            event_log=runtime.event_log,
            run_id="cli:environment_repair",
        )
        after_events = runtime.event_log.query()[before:]
        recheck = result.graph.nodes.get("recheck")
        recheck_payload = dict(recheck.payload) if recheck else {}
        shape_fields: dict[str, Any] = {}
        if bind is not None:
            template = get_recipe("environment_repair")
            observed = observe_instantiated_recipe(bind, result.graph, template)
            shape_fields = dict(observed["fields"])
        fields = {
            **shape_fields,
            "template_name": "environment_repair",
            "environment_ok": bool(recheck_payload.get("environment_ok")),
            "recheck_ok": bool(recheck_payload.get("recheck_ok")),
            "repair_attempts": int(recheck_payload.get("repair_attempts") or 0),
            "budget_spent": float(result.budget_spent),
        }
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status=result.status,
            event_types=[e.type for e in after_events],
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="environment_repair" in catalog,
            subgraph_node_ids=list(result.graph.nodes),
            cost_units=float(result.budget_spent),
            fields=fields,
        )


class InitializePreflightRecipeAdapter(CliRecipeAdapter):
    """Execute ``initialize_preflight``: linkage → capability → checkpoint → ready."""

    name = "initialize_preflight"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from pathlib import Path

        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.initialize_preflight_runner import initialize_preflight_runners
        from mechaharness.recipe_bind import RecipeBind, observe_instantiated_recipe
        from mechaharness.recipe_runner import get_recipe, list_recipes, run_recipe

        catalog = {row["name"] for row in list_recipes()}
        soft: dict[str, Any] = dict(body.soft_bindings or {})
        inputs: dict[str, Any] = {}
        goal = "initialize_preflight"
        bind: RecipeBind | None = None
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
            "initialize_preflight",
            params=params,
            runners=initialize_preflight_runners(),
            event_log=runtime.event_log,
            run_id="cli:initialize_preflight",
        )
        after_events = runtime.event_log.query()[before:]
        ready = result.graph.nodes.get("ready")
        ready_payload = dict(ready.payload) if ready else {}
        shape_fields: dict[str, Any] = {}
        if bind is not None:
            template = get_recipe("initialize_preflight")
            observed = observe_instantiated_recipe(bind, result.graph, template)
            shape_fields = dict(observed["fields"])
        fields = {
            **shape_fields,
            "template_name": "initialize_preflight",
            "preflight_ok": bool(ready_payload.get("preflight_ok")),
            "ready": bool(ready_payload.get("ready")),
            "budget_spent": float(result.budget_spent),
        }
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status=result.status,
            event_types=[e.type for e in after_events],
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="initialize_preflight" in catalog,
            subgraph_node_ids=list(result.graph.nodes),
            cost_units=float(result.budget_spent),
            fields=fields,
        )


class ProduceCritiqueRefineRecipeAdapter(CliRecipeAdapter):
    """Execute ``produce_critique_refine``: produce → critique → refine → complete."""

    name = "produce_critique_refine"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from pathlib import Path

        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.produce_critique_refine_runner import (
            produce_critique_refine_runners,
        )
        from mechaharness.recipe_bind import RecipeBind, observe_instantiated_recipe
        from mechaharness.recipe_runner import get_recipe, list_recipes, run_recipe

        catalog = {row["name"] for row in list_recipes()}
        soft: dict[str, Any] = dict(body.soft_bindings or {})
        inputs: dict[str, Any] = {}
        acceptance: list[Any] = []
        goal = "produce_critique_refine"
        bind: RecipeBind | None = None
        if body.path:
            base = getattr(runtime, "bind_base_dir", None)
            path = Path(body.path)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            bind = RecipeBind.from_path(path)
            soft = {**bind.soft_bindings, **soft}
            inputs = dict(bind.inputs)
            acceptance = list(bind.acceptance)
            goal = bind.goal or bind.name or goal
        params = GraphTemplateParams(
            goal=goal,
            soft_bindings=soft,
            inputs=inputs,
            acceptance=acceptance,
            stop_contract=bind.stop_contract if bind is not None else None,
        )
        before = len(runtime.event_log.query())
        result = await run_recipe(
            "produce_critique_refine",
            params=params,
            runners=produce_critique_refine_runners(),
            event_log=runtime.event_log,
            run_id="cli:produce_critique_refine",
        )
        after_events = runtime.event_log.query()[before:]
        complete = result.graph.nodes.get("complete")
        complete_payload = dict(complete.payload) if complete else {}
        shape_fields: dict[str, Any] = {}
        if bind is not None:
            template = get_recipe("produce_critique_refine")
            observed = observe_instantiated_recipe(bind, result.graph, template)
            shape_fields = dict(observed["fields"])
        fields = {
            **shape_fields,
            "template_name": "produce_critique_refine",
            "rounds_used": int(complete_payload.get("rounds_used") or 0),
            "findings_cleared": bool(complete_payload.get("findings_cleared")),
            "final_status": complete_payload.get("final_status") or result.status,
            "budget_spent": float(result.budget_spent),
        }
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status=result.status,
            event_types=[e.type for e in after_events],
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="produce_critique_refine" in catalog,
            subgraph_node_ids=list(result.graph.nodes),
            cost_units=float(result.budget_spent),
            fields=fields,
        )


class SafetyEvalRecipeAdapter(CliRecipeAdapter):
    """Execute ``safety_eval``: produce → review → score."""

    name = "safety_eval"

    async def run(self, body: RunRecipeCommand, runtime: Any) -> Any:
        from pathlib import Path

        from mechaharness.cli_instrumentor import CliStepResult
        from mechaharness.graph_templates import GraphTemplateParams
        from mechaharness.recipe_bind import RecipeBind, observe_instantiated_recipe
        from mechaharness.recipe_runner import get_recipe, list_recipes, run_recipe
        from mechaharness.safety_eval_runner import safety_eval_runners

        catalog = {row["name"] for row in list_recipes()}
        soft: dict[str, Any] = dict(body.soft_bindings or {})
        inputs: dict[str, Any] = {}
        acceptance: list[Any] = []
        goal = "safety_eval"
        bind: RecipeBind | None = None
        if body.path:
            base = getattr(runtime, "bind_base_dir", None)
            path = Path(body.path)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            bind = RecipeBind.from_path(path)
            soft = {**bind.soft_bindings, **soft}
            inputs = dict(bind.inputs)
            acceptance = list(bind.acceptance)
            goal = bind.goal or bind.name or goal
        params = GraphTemplateParams(
            goal=goal,
            soft_bindings=soft,
            inputs=inputs,
            acceptance=acceptance,
        )
        before = len(runtime.event_log.query())
        result = await run_recipe(
            "safety_eval",
            params=params,
            runners=safety_eval_runners(),
            event_log=runtime.event_log,
            run_id="cli:safety_eval",
        )
        after_events = runtime.event_log.query()[before:]
        score = result.graph.nodes.get("score")
        score_payload = dict(score.payload) if score else {}
        shape_fields: dict[str, Any] = {}
        if bind is not None:
            template = get_recipe("safety_eval")
            observed = observe_instantiated_recipe(bind, result.graph, template)
            shape_fields = dict(observed["fields"])
        fields = {
            **shape_fields,
            "template_name": "safety_eval",
            "safety_report": score_payload.get("safety_report"),
            "outcome": score_payload.get("outcome"),
            "severity": score_payload.get("severity"),
            "budget_spent": float(result.budget_spent),
        }
        return CliStepResult(
            verb="run_recipe",
            text=None,
            status=result.status,
            event_types=[e.type for e in after_events],
            clock_iso=runtime.datetime_service.now_utc_iso(),
            recipe_in_catalog="safety_eval" in catalog,
            subgraph_node_ids=list(result.graph.nodes),
            cost_units=float(result.budget_spent),
            fields=fields,
        )


def default_cli_recipe_adapter_classes() -> dict[str, type[CliRecipeAdapter]]:
    return {
        HarnessRunRecipeAdapter.name: HarnessRunRecipeAdapter,
        BackendDescribeRecipeAdapter.name: BackendDescribeRecipeAdapter,
        ConversationalToolLoopRecipeAdapter.name: ConversationalToolLoopRecipeAdapter,
        ContextPackRecipeAdapter.name: ContextPackRecipeAdapter,
        DecisionPlaneRecipeAdapter.name: DecisionPlaneRecipeAdapter,
        VerifyRepairRecipeAdapter.name: VerifyRepairRecipeAdapter,
        BoundedRetryRecipeAdapter.name: BoundedRetryRecipeAdapter,
        IndependentReviewRecipeAdapter.name: IndependentReviewRecipeAdapter,
        EnvironmentRepairRecipeAdapter.name: EnvironmentRepairRecipeAdapter,
        InitializePreflightRecipeAdapter.name: InitializePreflightRecipeAdapter,
        ProduceCritiqueRefineRecipeAdapter.name: ProduceCritiqueRefineRecipeAdapter,
        SafetyEvalRecipeAdapter.name: SafetyEvalRecipeAdapter,
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
    "BoundedRetryRecipeAdapter",
    "CliRecipeAdapter",
    "ContextPackRecipeAdapter",
    "ConversationalToolLoopRecipeAdapter",
    "DecisionPlaneRecipeAdapter",
    "EnvironmentRepairRecipeAdapter",
    "HarnessRunRecipeAdapter",
    "IndependentReviewRecipeAdapter",
    "InitializePreflightRecipeAdapter",
    "ProduceCritiqueRefineRecipeAdapter",
    "SafetyEvalRecipeAdapter",
    "VerifyRepairRecipeAdapter",
    "default_cli_recipe_adapter_classes",
    "resolve_cli_recipe_adapters",
]
