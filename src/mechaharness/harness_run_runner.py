"""Node runners for the ``harness_run`` and ``backend_describe`` recipes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mechaharness.config import Settings
from mechaharness.factory import describe as describe_backend
from mechaharness.factory import settings_from_request
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.harness.base import AbstractHarness


def _settings_from_payload(payload: dict[str, Any]) -> Settings:
    """Build Settings from a recipe node payload (CLI / recipe bindings)."""
    from mechaharness.core.contract import RunRequest

    request = RunRequest(
        prompt=str(payload.get("prompt") or ""),
        backend=payload.get("backend"),
        family=payload.get("family"),
        model=payload.get("model"),
        api_key=payload.get("api_key"),
        base_url=payload.get("base_url"),
        system_prompt=payload.get("system_prompt"),
        max_turns=int(payload.get("max_turns") or 8),
        temperature=payload.get("temperature"),
    )
    return settings_from_request(request)


class HarnessPrepareRunner(GraphNodeRunner):
    """Validate / echo prepare payload for the harness_run pipeline."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["harness_prepare"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        prompt = str(node.payload.get("prompt") or "")
        if not prompt.strip():
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error="harness_prepare requires a non-empty prompt",
                payload=dict(node.payload),
            )
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={**dict(node.payload), "prepared": True},
        )


class HarnessLoopRunner(GraphNodeRunner):
    """Run an injected :class:`~mechaharness.harness.base.AbstractHarness`.

    Prefer constructor injection of a live harness (DI / recipe_runner). When
    ``harness`` is omitted, hosts must supply one before execute.
    """

    def __init__(
        self,
        *,
        harness: AbstractHarness | None = None,
        kinds: Sequence[str] | None = None,
    ) -> None:
        self._harness = harness
        self._kinds = list(kinds or ["harness_loop"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    def bind_harness(self, harness: AbstractHarness) -> None:
        """Late-bind harness for recipe_runner after DI construct."""
        self._harness = harness

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        if self._harness is None:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error="harness_loop runner has no AbstractHarness bound",
                payload=dict(node.payload),
            )
        prompt = str(node.payload.get("prompt") or "")
        result = await self._harness.run(prompt)
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "final_text": result.final_text,
                "turns": result.turns,
                "messages": [m.model_dump(mode="json") for m in result.messages],
                "events": [e.model_dump(mode="json") for e in result.events],
            },
        )


class HarnessRenderRunner(GraphNodeRunner):
    """Pack final text / transcript from the upstream harness_loop node."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["harness_render"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        loop_payload: dict[str, Any] = {}
        for dep_id in node.depends_on:
            dep = context.graph.nodes.get(dep_id)
            if dep is None:
                continue
            if (
                dep.payload.get("final_text") is not None
                or dep.kind in {"harness_loop"}
                or "turns" in dep.payload
            ):
                loop_payload = dict(dep.payload)
                break
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                **dict(node.payload),
                "final_text": loop_payload.get("final_text"),
                "turns": loop_payload.get("turns", 0),
                "messages": loop_payload.get("messages") or [],
                "events": loop_payload.get("events") or [],
            },
        )


class BackendDescribeRunner(GraphNodeRunner):
    """Instantiate an inference Strategy and return ``describe()`` metadata."""

    def __init__(self, *, kinds: Sequence[str] | None = None) -> None:
        self._kinds = list(kinds or ["backend_describe"])

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    def required_grants(self) -> Sequence[object]:
        return []

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        del context
        backend = node.payload.get("backend")
        if not backend:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error="backend_describe requires payload.backend",
                payload=dict(node.payload),
            )
        settings = _settings_from_payload(dict(node.payload))
        meta = await describe_backend(settings)
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={**dict(node.payload), "description": meta},
        )
