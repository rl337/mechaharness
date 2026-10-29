"""Graph node runner for ``cli:infer`` (reason-lane Completer)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.cli_universe import CLI_INFER_KIND
from mechaharness.context_spec import (
    ContextSpecError,
    compile_context_spec,
    context_spec_from_mapping,
    freeze_bag_snapshot,
    publish_response_to_bag,
)
from mechaharness.core.access import CapabilityProfile, CostAccountant, default_capability_profile
from mechaharness.core.completer import Completer
from mechaharness.core.events import Event, EventLog, Inference, event_type_key
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    Usage,
)
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome

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
    ) -> None:
        self._scripts = {str(k): str(v) for k, v in scripts.items()}
        self._fallback = fallback
        self.requests: list[CompletionRequest] = []

    def capability_profile(self) -> CapabilityProfile:
        if hasattr(self._fallback, "capability_profile"):
            return self._fallback.capability_profile()
        return default_capability_profile()

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        node_id = request.extra.get("node_id")
        if isinstance(node_id, str) and node_id in self._scripts:
            return CompletionResponse(
                message=ChatMessage(
                    role=Role.ASSISTANT, content=self._scripts[node_id]
                ),
                finish_reason="stop",
                usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
        return await self._fallback.complete(request)


class CliInferRunner(GraphNodeRunner):
    """One-shot chat completion; emits ``core:inference`` and prices ``core:cost``.

    Legacy payload: ``prompt`` / ``system`` (no bag).

    Bag-aware payload (M2): ``context`` (:class:`~mechaharness.context_spec.ContextSpec`
    mapping) compiles an immutable bag snapshot into the Completer request and
    publishes the response to ``context.response.writes``.
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
        # Last compile artifacts for story / host observation (node_id → dict).
        self.last_model_inputs: dict[str, dict[str, Any]] = {}
        self.last_requests: dict[str, CompletionRequest] = {}

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

        request = CompletionRequest(
            model=model,
            messages=list(compiled.messages),
            extra={"node_id": node.id, "snapshot_id": snapshot_id},
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
        }
        return await self._complete_and_finish(
            node,
            context=context,
            request=request,
            response_spec=spec.response,
            snapshot_id=compiled.snapshot_id,
        )

    async def _complete_and_finish(
        self,
        node: GraphNode,
        *,
        context: GraphRunContext,
        request: CompletionRequest,
        response_spec: Any | None,
        snapshot_id: str | None,
    ) -> NodeOutcome:
        self.last_requests[node.id] = request
        response = await self._completer.complete(request)

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

        inference_payload: dict[str, Any] = {
            "completer": str(completer_name),
            "model": request.model,
            "finish_reason": response.finish_reason,
            "content": text,
            "parent_node_id": node.id,
            "component_id": f"{node.id}/inference:1",
            "execution_node_id": node.id,
        }
        if snapshot_id is not None:
            inference_payload["snapshot_id"] = snapshot_id
        if publish_path is not None:
            inference_payload["bag_write"] = publish_path
        if assistant.reasoning_content:
            inference_payload["reasoning_content"] = assistant.reasoning_content
        inference_payload["usage"] = Usage.for_event(response.usage)
        self._event_log.emit(
            Event(
                type=event_type_key(Inference),
                agent_id=context.agent_id,
                run_id=context.run_id,
                parent_agent_id=context.parent_agent_id,
                payload=inference_payload,
            )
        )
        outcome_payload: dict[str, Any] = {
            "text": text,
            "finish_reason": response.finish_reason,
        }
        if snapshot_id is not None:
            outcome_payload["snapshot_id"] = snapshot_id
        if publish_path is not None:
            outcome_payload["bag_write"] = publish_path
            outcome_payload["published"] = published
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload=outcome_payload)


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
