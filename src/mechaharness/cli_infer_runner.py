"""Graph node runner for ``cli:infer`` (reason-lane Completer)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.bag_inspect import (
    InspectionPolicy,
    PriorResponseRecord,
    SnapshotInspectionToolkit,
    inspection_policy_from_mapping,
    new_invocation_id,
)
from mechaharness.cli_universe import CLI_INFER_KIND
from mechaharness.context_spec import (
    ContextSpecError,
    compile_context_spec,
    context_spec_from_mapping,
    freeze_bag_snapshot,
    publish_response_to_bag,
)
from mechaharness.core.access import (
    CapabilityProfile,
    CostAccountant,
    default_capability_profile,
)
from mechaharness.core.completer import Completer
from mechaharness.core.events import Event, EventLog, Inference, event_type_key
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    ToolCall,
    Usage,
)
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.walk_bag import WalkBag

# Story / bag-walk alias: same runner, open kind string hosts may use in YAML.
INFER_KIND = "infer"
DEFAULT_INFER_KINDS: tuple[str, ...] = (CLI_INFER_KIND, INFER_KIND)


class NodeScriptedCompleter(Completer):
    """Completer that returns scripted text keyed by ``request.extra['node_id']``.

    Used by stepped ``graph_walk`` stories so bag-aware ``cli:infer`` nodes can
    publish structured JSON through the real Completer path. Unscripted nodes
    fall through to ``fallback``.
    """

    name = "node_scripted"

    def __init__(
        self,
        scripts: Mapping[str, str],
        fallback: Completer,
        *,
        turns: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        self._scripts = {str(k): str(v) for k, v in scripts.items()}
        self._fallback = fallback
        self._turns: dict[str, list[Mapping[str, Any]]] = {
            str(k): [dict(item) for item in seq] for k, seq in (turns or {}).items()
        }
        self.requests: list[CompletionRequest] = []

    def capability_profile(self) -> CapabilityProfile:
        if hasattr(self._fallback, "capability_profile"):
            return self._fallback.capability_profile()
        return default_capability_profile()

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        node_id = request.extra.get("node_id")
        if isinstance(node_id, str) and self._turns.get(node_id):
            turn = self._turns[node_id].pop(0)
            return _response_from_turn(turn)
        if isinstance(node_id, str) and node_id in self._scripts:
            return CompletionResponse(
                message=ChatMessage(
                    role=Role.ASSISTANT, content=self._scripts[node_id]
                ),
                finish_reason="stop",
                usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
        return await self._fallback.complete(request)


def _response_from_turn(turn: Mapping[str, Any]) -> CompletionResponse:
    raw_calls = turn.get("tool_calls")
    tool_calls: list[ToolCall] | None = None
    if isinstance(raw_calls, list) and raw_calls:
        tool_calls = []
        for index, item in enumerate(raw_calls):
            data = dict(item)
            tool_calls.append(
                ToolCall(
                    id=str(data.get("id") or f"call-{index + 1}"),
                    name=str(data.get("name") or ""),
                    arguments=dict(data.get("arguments") or {}),
                )
            )
    content = turn.get("content")
    text: str | None
    if content is None:
        text = None
    elif isinstance(content, (dict, list)):
        text = json.dumps(content, sort_keys=True)
    else:
        text = str(content)
    return CompletionResponse(
        message=ChatMessage(
            role=Role.ASSISTANT,
            content=text,
            tool_calls=tool_calls,
        ),
        finish_reason="tool_calls" if tool_calls else "stop",
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


class CliInferRunner(GraphNodeRunner):
    """One-shot chat completion; emits ``core:inference`` and prices ``core:cost``.

    Legacy payload: ``prompt`` / ``system`` (no bag).

    Bag-aware payload (M2): ``context`` (:class:`~mechaharness.context_spec.ContextSpec`
    mapping) compiles an immutable bag snapshot into the Completer request and
    publishes the response to ``context.response.writes``.

    Inspection payload (M3): optional ``inspection`` binds snapshot-only
    ``inspect_bag`` / ``inspect_prior_response`` tools for a bounded tool loop.
    """

    def __init__(
        self,
        completer: Completer,
        cost: CostAccountant,
        event_log: EventLog,
        *,
        model: str = "cli-default",
        kinds: Sequence[str] | None = None,
    ) -> None:
        self._completer = completer
        self._cost = cost
        self._event_log = event_log
        self._model = model
        self._kinds = list(kinds) if kinds is not None else [CLI_INFER_KIND]
        self.last_model_inputs: dict[str, dict[str, Any]] = {}
        self.last_requests: dict[str, CompletionRequest] = {}
        self.last_inference: dict[str, dict[str, Any]] = {}
        self.prior_responses: dict[str, PriorResponseRecord] = {}

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        if node.payload.get("context") is not None:
            return await self._run_bag_aware(node, context=context)
        return await self._run_legacy_prompt(node, context=context)

    async def _run_legacy_prompt(
        self, node: GraphNode, *, context: GraphRunContext
    ) -> NodeOutcome:
        prompt = str(node.payload.get("prompt") or "").strip()
        if not prompt:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error="cli_infer_missing_prompt",
            )
        system = str(node.payload.get("system") or "")
        messages: list[ChatMessage] = []
        if system.strip():
            messages.append(ChatMessage(role=Role.SYSTEM, content=system))
        messages.append(ChatMessage(role=Role.USER, content=prompt))
        model = str(node.payload.get("model") or self._model)
        request = CompletionRequest(
            model=model,
            messages=messages,
            extra={"node_id": node.id},
        )
        return await self._complete_and_finish(
            node,
            context=context,
            request=request,
            response_spec=None,
            snapshot_id=None,
            invocation_id=new_invocation_id(),
            toolkit=None,
        )

    async def _run_bag_aware(
        self, node: GraphNode, *, context: GraphRunContext
    ) -> NodeOutcome:
        try:
            spec = context_spec_from_mapping(node.payload["context"])
        except Exception as exc:  # noqa: BLE001 — surface as node failure
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error=f"cli_infer_bad_context_spec:{exc}",
            )
        snapshot_id, frozen = freeze_bag_snapshot(context.bag)
        model = str(node.payload.get("model") or self._model)
        try:
            compiled = compile_context_spec(
                frozen,
                spec,
                snapshot_id=snapshot_id,
                model=model,
                run_id=context.run_id,
                node_id=node.id,
            )
        except ContextSpecError as exc:
            return NodeOutcome(status=NodeStatus.FAILED, error=str(exc))

        invocation_id = new_invocation_id()
        toolkit: SnapshotInspectionToolkit | None = None
        tools = None
        inspection_raw = node.payload.get("inspection")
        if inspection_raw is not None:
            policy = inspection_policy_from_mapping(inspection_raw)
            allowed_ids = policy.allowed_invocation_ids
            if allowed_ids is None:
                # Default: every recorded prior response in this walk.
                allowed_ids = list(self.prior_responses)
                policy = policy.model_copy(update={"allowed_invocation_ids": allowed_ids})
            toolkit = SnapshotInspectionToolkit(
                frozen,
                snapshot_id=snapshot_id,
                policy=policy,
                prior_responses=self.prior_responses,
            )
            tools = toolkit.tool_definitions()

        request = CompletionRequest(
            model=model,
            messages=list(compiled.messages),
            tools=tools,
            extra={
                "node_id": node.id,
                "snapshot_id": snapshot_id,
                "invocation_id": invocation_id,
            },
        )
        self.last_model_inputs[node.id] = {
            "snapshot_id": compiled.snapshot_id,
            "content_hash": compiled.content_hash,
            "included_paths": list(compiled.included_paths),
            "omitted_paths": list(compiled.omitted_paths),
            "messages": [
                {
                    "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                    "content": m.content,
                }
                for m in compiled.messages
            ],
            "manifest": compiled.manifest.model_dump(mode="json"),
            "includes_verified_discovery": _includes_verified_discovery(
                compiled.included_paths
            ),
            "includes_unrelated_bag_data": _includes_unrelated_bag_data(
                compiled.included_paths
            ),
            "tool_definitions": [t.model_dump(mode="json") for t in (tools or [])],
        }
        if toolkit is None:
            return await self._complete_and_finish(
                node,
                context=context,
                request=request,
                response_spec=spec.response,
                snapshot_id=compiled.snapshot_id,
                invocation_id=invocation_id,
                toolkit=None,
            )
        return await self._run_inspection_loop(
            node,
            context=context,
            request=request,
            response_spec=spec.response,
            snapshot_id=compiled.snapshot_id,
            invocation_id=invocation_id,
            toolkit=toolkit,
            policy=inspection_policy_from_mapping(inspection_raw),
        )

    async def _run_inspection_loop(
        self,
        node: GraphNode,
        *,
        context: GraphRunContext,
        request: CompletionRequest,
        response_spec: Any,
        snapshot_id: str,
        invocation_id: str,
        toolkit: SnapshotInspectionToolkit,
        policy: InspectionPolicy,
    ) -> NodeOutcome:
        messages = list(request.messages)
        tools = list(request.tools or [])
        mutate_live = node.payload.get("mutate_live_after_first_inspect")
        mutated = False
        first_inspect_value: Any = None
        second_inspect_value: Any = None
        inspect_count = 0
        max_rounds = max(1, int(policy.max_tool_calls) + 1)
        final_text = ""
        last_request = request

        for _ in range(max_rounds):
            last_request = CompletionRequest(
                model=request.model,
                messages=list(messages),
                tools=tools,
                extra=dict(request.extra),
            )
            response = await self._completer.complete(last_request)
            self._price(response, context=context)
            assistant = response.message
            messages.append(assistant)
            calls = list(assistant.tool_calls or [])
            if not calls:
                final_text = assistant.content or ""
                break
            for call in calls:
                outcome = toolkit.dispatch(call.name, call.arguments)
                if (
                    call.name == SnapshotInspectionToolkit.INSPECT_BAG
                    and outcome.status in {"ok", "truncated"}
                ):
                    inspect_count += 1
                    if inspect_count == 1:
                        first_inspect_value = outcome.value
                        if isinstance(mutate_live, dict) and not mutated:
                            _apply_live_mutation(context.bag, mutate_live)
                            mutated = True
                    elif inspect_count == 2:
                        second_inspect_value = outcome.value
                messages.append(
                    ChatMessage(
                        role=Role.TOOL,
                        tool_call_id=call.id,
                        content=outcome.model_dump_json(),
                        name=call.name,
                    )
                )
        else:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error="cli_infer_tool_loop_exhausted",
            )

        published: Any = None
        publish_path = response_spec.writes
        try:
            published = publish_response_to_bag(context.bag, response_spec, final_text)
        except ContextSpecError as exc:
            return NodeOutcome(status=NodeStatus.FAILED, error=str(exc))

        self.prior_responses[invocation_id] = PriorResponseRecord(
            invocation_id=invocation_id,
            snapshot_id=snapshot_id,
            node_id=node.id,
            content=final_text,
            published=published,
            bag_write=publish_path,
        )
        self.last_requests[node.id] = last_request
        flags = {
            "invocation_id": invocation_id,
            "snapshot_id": snapshot_id,
            "tool_call_count": len(toolkit.transcript),
            "tool_results_in_transcript": bool(toolkit.transcript),
            "unauthorized_inspection_denied": any(
                item.get("status") == "denied" for item in toolkit.transcript
            ),
            "inspection_snapshot_stable": (
                first_inspect_value is not None
                and second_inspect_value is not None
                and first_inspect_value == second_inspect_value
                and mutated
            ),
            "transcript": list(toolkit.transcript),
            "tool_definitions_count": len(tools),
        }
        self.last_inference[node.id] = flags
        self._emit_inference(
            node,
            context=context,
            model=request.model,
            text=final_text,
            finish_reason="stop",
            snapshot_id=snapshot_id,
            publish_path=publish_path,
            usage=None,
            extra={"invocation_id": invocation_id, **flags},
        )
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                "text": final_text,
                "finish_reason": "stop",
                "snapshot_id": snapshot_id,
                "bag_write": publish_path,
                "published": published,
                "invocation_id": invocation_id,
                **flags,
            },
        )

    async def _complete_and_finish(
        self,
        node: GraphNode,
        *,
        context: GraphRunContext,
        request: CompletionRequest,
        response_spec: Any | None,
        snapshot_id: str | None,
        invocation_id: str,
        toolkit: SnapshotInspectionToolkit | None,
    ) -> NodeOutcome:
        del toolkit
        self.last_requests[node.id] = request
        response = await self._completer.complete(request)
        self._price(response, context=context)

        assistant = response.message
        text = assistant.content or ""
        published: Any = None
        publish_path: str | None = None
        if response_spec is not None:
            publish_path = response_spec.writes
            try:
                published = publish_response_to_bag(context.bag, response_spec, text)
            except ContextSpecError as exc:
                return NodeOutcome(status=NodeStatus.FAILED, error=str(exc))

        if publish_path is not None:
            self.prior_responses[invocation_id] = PriorResponseRecord(
                invocation_id=invocation_id,
                snapshot_id=snapshot_id,
                node_id=node.id,
                content=text,
                published=published,
                bag_write=publish_path,
            )

        flags = {
            "invocation_id": invocation_id,
            "tool_call_count": 0,
            "tool_results_in_transcript": False,
            "unauthorized_inspection_denied": False,
            "inspection_snapshot_stable": False,
            "tool_definitions_count": len(request.tools or []),
            "transcript": [],
        }
        self.last_inference[node.id] = {
            **flags,
            "snapshot_id": snapshot_id,
        }
        self._emit_inference(
            node,
            context=context,
            model=request.model,
            text=text,
            finish_reason=response.finish_reason,
            snapshot_id=snapshot_id,
            publish_path=publish_path,
            usage=response.usage,
            extra={"invocation_id": invocation_id},
            reasoning=assistant.reasoning_content,
        )
        outcome_payload: dict[str, Any] = {
            "text": text,
            "finish_reason": response.finish_reason,
            **flags,
        }
        if snapshot_id is not None:
            outcome_payload["snapshot_id"] = snapshot_id
        if publish_path is not None:
            outcome_payload["bag_write"] = publish_path
            outcome_payload["published"] = published
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload=outcome_payload)

    def _price(
        self, response: CompletionResponse, *, context: GraphRunContext
    ) -> None:
        completer_name = getattr(self._completer, "name", None) or type(
            self._completer
        ).__name__
        profile = (
            self._completer.capability_profile()
            if hasattr(self._completer, "capability_profile")
            else None
        )
        if profile is not None:
            self._cost.price_inference(
                str(completer_name),
                profile,
                agent_id=context.agent_id,
                run_id=context.run_id,
                parent_agent_id=context.parent_agent_id,
                usage=response.usage,
            )

    def _emit_inference(
        self,
        node: GraphNode,
        *,
        context: GraphRunContext,
        model: str,
        text: str,
        finish_reason: str | None,
        snapshot_id: str | None,
        publish_path: str | None,
        usage: Usage | None,
        extra: Mapping[str, Any] | None = None,
        reasoning: str | None = None,
    ) -> None:
        completer_name = getattr(self._completer, "name", None) or type(
            self._completer
        ).__name__
        inference_payload: dict[str, Any] = {
            "completer": str(completer_name),
            "model": model,
            "finish_reason": finish_reason,
            "content": text,
            "parent_node_id": node.id,
            "component_id": f"{node.id}/inference:1",
            "execution_node_id": node.id,
        }
        if snapshot_id is not None:
            inference_payload["snapshot_id"] = snapshot_id
        if publish_path is not None:
            inference_payload["bag_write"] = publish_path
        if reasoning:
            inference_payload["reasoning_content"] = reasoning
        if extra:
            inference_payload.update(dict(extra))
        inference_payload["usage"] = Usage.for_event(usage)
        self._event_log.emit(
            Event(
                type=event_type_key(Inference),
                agent_id=context.agent_id,
                run_id=context.run_id,
                parent_agent_id=context.parent_agent_id,
                payload=inference_payload,
            )
        )


def _apply_live_mutation(bag: WalkBag, puts: Mapping[str, Any]) -> None:
    for key, value in puts.items():
        key_s = str(key)
        if "." in key_s:
            bag.path_put(key_s, value)
        else:
            bag.put(key_s, value)


def _includes_verified_discovery(included_paths: Sequence[str]) -> bool:
    return any("verified" in path for path in included_paths)


def _includes_unrelated_bag_data(included_paths: Sequence[str]) -> bool:
    return any(
        "noise" in path or "unrelated" in path for path in included_paths
    )


__all__ = [
    "DEFAULT_INFER_KINDS",
    "INFER_KIND",
    "CliInferRunner",
    "NodeScriptedCompleter",
]
