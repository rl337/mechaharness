"""Bag-aware judge node runner: ContextSpec compile, no tools (gastronomic M3)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mechaharness.bag_inspect import PriorResponseRecord, new_invocation_id
from mechaharness.cli_infer_runner import (
    _includes_unrelated_bag_data,
    _includes_verified_discovery,
)
from mechaharness.context_spec import (
    ContextSpecError,
    compile_context_spec,
    context_spec_from_mapping,
    freeze_bag_snapshot,
    publish_response_to_bag,
)
from mechaharness.core.access import CostAccountant
from mechaharness.core.completer import Completer
from mechaharness.core.events import Event, EventLog, Inference, event_type_key
from mechaharness.core.types import CompletionRequest, Usage
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome

JUDGE_KIND = "judge"
CLI_JUDGE_KIND = "cli:judge"
DEFAULT_JUDGE_KINDS: tuple[str, ...] = (JUDGE_KIND, CLI_JUDGE_KIND)


class CliJudgeRunner(GraphNodeRunner):
    """Compile bag evidence into a Completer request with **zero** tools.

    Publishes a structured judgment to ``context.response.writes``. Missing or
    invalid verdicts fail closed (never an automatic pass).
    """

    def __init__(
        self,
        completer: Completer,
        cost: CostAccountant,
        event_log: EventLog,
        *,
        model: str = "cli-judge",
        kinds: Sequence[str] | None = None,
        prior_responses: dict[str, PriorResponseRecord] | None = None,
    ) -> None:
        self._completer = completer
        self._cost = cost
        self._event_log = event_log
        self._model = model
        self._kinds = list(kinds) if kinds is not None else list(DEFAULT_JUDGE_KINDS)
        self.prior_responses = prior_responses if prior_responses is not None else {}
        self.last_model_inputs: dict[str, dict[str, Any]] = {}
        self.last_requests: dict[str, CompletionRequest] = {}
        self.last_inference: dict[str, dict[str, Any]] = {}

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        if node.payload.get("context") is None:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error="cli_judge_missing_context",
            )
        try:
            spec = context_spec_from_mapping(node.payload["context"])
        except Exception as exc:  # noqa: BLE001
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error=f"cli_judge_bad_context_spec:{exc}",
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
        # Judge contract: never attach tools.
        request = CompletionRequest(
            model=model,
            messages=list(compiled.messages),
            tools=None,
            extra={
                "node_id": node.id,
                "snapshot_id": snapshot_id,
                "invocation_id": invocation_id,
                "judge": True,
            },
        )
        self.last_requests[node.id] = request
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
            "includes_verified_evidence": (
                _includes_verified_discovery(compiled.included_paths)
                or any("evidence" in p for p in compiled.included_paths)
            ),
            "includes_unrelated_bag_data": _includes_unrelated_bag_data(
                compiled.included_paths
            ),
            "tool_definitions": [],
        }

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

        if response.message.tool_calls:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error="cli_judge_tools_not_allowed",
            )

        text = response.message.content or ""
        try:
            published = publish_response_to_bag(context.bag, spec.response, text)
        except ContextSpecError as exc:
            return NodeOutcome(status=NodeStatus.FAILED, error=str(exc))

        if not _valid_judgment(published):
            return NodeOutcome(
                status=NodeStatus.FAILED,
                error="cli_judge_invalid_verdict",
            )

        tool_call_count = 0
        flags = {
            "invocation_id": invocation_id,
            "snapshot_id": snapshot_id,
            "tool_call_count": tool_call_count,
            "tool_definitions_count": 0,
            "includes_verified_evidence": self.last_model_inputs[node.id][
                "includes_verified_evidence"
            ],
            "judgment_valid": bool(
                isinstance(published, dict) and published.get("valid") is True
            ),
            "abstained": bool(
                isinstance(published, dict)
                and (
                    published.get("abstain") is True
                    or published.get("verdict") == "abstain"
                )
            ),
        }
        self.last_inference[node.id] = flags
        self.prior_responses[invocation_id] = PriorResponseRecord(
            invocation_id=invocation_id,
            snapshot_id=snapshot_id,
            node_id=node.id,
            content=text,
            published=published,
            bag_write=spec.response.writes,
        )

        self._event_log.emit(
            Event(
                type=event_type_key(Inference),
                agent_id=context.agent_id,
                run_id=context.run_id,
                parent_agent_id=context.parent_agent_id,
                payload={
                    "completer": str(completer_name),
                    "model": model,
                    "finish_reason": response.finish_reason,
                    "content": text,
                    "parent_node_id": node.id,
                    "component_id": f"{node.id}/judge:1",
                    "execution_node_id": node.id,
                    "snapshot_id": snapshot_id,
                    "bag_write": spec.response.writes,
                    "judge": True,
                    "tool_call_count": 0,
                    "usage": Usage.for_event(response.usage),
                    **flags,
                },
            )
        )
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                "text": text,
                "finish_reason": response.finish_reason,
                "bag_write": spec.response.writes,
                "published": published,
                **flags,
            },
        )


def _valid_judgment(published: Any) -> bool:
    """Accept only explicit typed verdicts; never invent a pass."""
    if not isinstance(published, dict):
        return False
    if published.get("abstain") is True or published.get("verdict") == "abstain":
        return "reason" in published or "evidence_refs" in published
    if "valid" not in published:
        return False
    return isinstance(published.get("valid"), bool)


__all__ = [
    "CLI_JUDGE_KIND",
    "DEFAULT_JUDGE_KINDS",
    "JUDGE_KIND",
    "CliJudgeRunner",
]
