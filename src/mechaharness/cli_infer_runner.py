"""Graph node runner for ``cli:infer`` (reason-lane Completer)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mechaharness.cli_universe import CLI_INFER_KIND
from mechaharness.core.access import CostAccountant
from mechaharness.core.completer import Completer
from mechaharness.core.events import Event, EventLog, Inference, event_type_key
from mechaharness.core.types import ChatMessage, CompletionRequest, Role, Usage
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome


class CliInferRunner(GraphNodeRunner):
    """One-shot chat completion; emits ``core:inference`` and prices ``core:cost``."""

    def __init__(
        self,
        completer: Completer,
        cost: CostAccountant,
        event_log: EventLog,
        *,
        model: str = "cli-default",
    ) -> None:
        self._completer = completer
        self._cost = cost
        self._event_log = event_log
        self._model = model

    def kinds(self) -> Sequence[str]:
        return [CLI_INFER_KIND]

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
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
        request = CompletionRequest(model=model, messages=messages)
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
        inference_payload: dict[str, Any] = {
            "completer": str(completer_name),
            "model": model,
            "finish_reason": response.finish_reason,
            "content": assistant.content,
            "parent_node_id": node.id,
            "component_id": f"{node.id}/inference:1",
            "execution_node_id": node.id,
        }
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
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                "text": assistant.content or "",
                "finish_reason": response.finish_reason,
            },
        )
