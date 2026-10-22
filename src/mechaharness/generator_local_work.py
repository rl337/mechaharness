"""Local work hook for :class:`~mechaharness.durable_graph_generator.DurableGraphGenerator`.

Between guidance yields (DG-13), the generator may run token-heavy work via an
injectable hook. Default is a no-op so offline stories stay model-free.
``ProjectCodingConfig`` binds a coding burst that expands a conversational
tool loop with workspace tools.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.conversational_tool_loop_runner import ConversationalToolLoopRunner
from mechaharness.core.access import FsRead, FsWrite, GraphExecute, ProcessExec
from mechaharness.durable_graph_generator import GeneratorRunRecord
from mechaharness.graph_templates.base import GraphTemplateParams
from mechaharness.graph_templates.conversational_tool_loop import (
    ConversationalToolLoopTemplate,
)
from mechaharness.tools.base import ToolRegistry


class GeneratorLocalWork(ABC):
    """Optional burst of local work after guidance is drained."""

    @abstractmethod
    def run(self, record: GeneratorRunRecord) -> dict[str, Any]:
        """Return a JSON-able payload merged into the completed yield."""


class NoOpGeneratorLocalWork(GeneratorLocalWork):
    """Default: no GraphExecutor work (M1 / offline durable stories)."""

    def run(self, record: GeneratorRunRecord) -> dict[str, Any]:
        del record
        return {"result": "ok"}


class ProjectCodingLocalWork(GeneratorLocalWork):
    """Run a conversational tool-loop burst with host coding tools.

    Used after ``guided_coding`` guidance is answered. ``complete`` returns an
    assistant-shaped dict (optionally with OpenAI-style ``tool_calls``).
    """

    def __init__(
        self,
        *,
        tools: ToolRegistry,
        complete: Any,
        max_iterations: int = 8,
    ) -> None:
        self._tools = tools
        self._complete = complete
        self._max_iterations = max_iterations

    def run(self, record: GeneratorRunRecord) -> dict[str, Any]:
        if record.recipe_id not in {"guided_coding", "conversational_tool_loop"}:
            return {"result": "ok", "skipped": True, "recipe_id": record.recipe_id}
        try:
            return asyncio.run(self._run_async(record))
        except Exception as exc:  # noqa: BLE001 - surface into completed/failed payload
            return {"result": "failed", "error": str(exc)}

    async def _run_async(self, record: GeneratorRunRecord) -> dict[str, Any]:
        guidance_text = _latest_guidance_text(record)
        goal = str(
            (record.inputs or {}).get("goal")
            or (record.inputs or {}).get("task")
            or record.recipe_id
        )
        messages = list((record.inputs or {}).get("messages") or [])
        if not messages:
            messages = [
                {
                    "role": "user",
                    "content": (
                        f"Task: {goal}\n"
                        f"Driver guidance: {guidance_text}\n"
                        "Use tools to implement the change under the workspace."
                    ),
                }
            ]

        def dispatch_tool(name: str, args: Any) -> str:
            try:
                tool = self._tools.get(name)
            except KeyError:
                return json.dumps({"ok": False, "error": f"unknown tool {name}"})
            arguments = args if isinstance(args, dict) else {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"raw": arguments}
            result = tool.handler(**arguments)
            return str(result)

        loop_runner = ConversationalToolLoopRunner(
            complete=self._complete,
            dispatch_tool=dispatch_tool,
        )
        max_iterations = int(
            (record.inputs or {}).get("max_iterations", self._max_iterations)
        )
        graph = ConversationalToolLoopTemplate().instantiate(
            GraphTemplateParams(
                goal=goal,
                inputs={"max_iterations": max_iterations, "messages": messages},
                soft_bindings={"max_iterations": max_iterations},
            )
        )
        tools_node = graph.nodes["tools"]
        tools_node.payload = {
            **dict(tools_node.payload or {}),
            "messages": messages,
            "max_iterations": max_iterations,
        }

        # Lazy import: host_kit → di → generator_local_work would cycle at import time.
        from mechaharness.host_kit import host_graph_executor

        grants = [FsRead, FsWrite, ProcessExec, GraphExecute]
        executor = host_graph_executor(runners=[loop_runner], grants=grants)
        result = await executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            envelope=CapabilityEnvelope.from_grants(grants),
            run_id=f"local:{record.run_id}",
            skip_linkage=True,
        )
        tools_out = graph.nodes["tools"].payload or {}
        return {
            "result": "ok" if result.status == "ok" else "failed",
            "graph_status": result.status,
            "goal": goal,
            "guidance": guidance_text,
            "rounds": tools_out.get("rounds"),
            "final_text": tools_out.get("final_text"),
            "error": result.error,
        }


def _latest_guidance_text(record: GeneratorRunRecord) -> str:
    if not record.guidance_history:
        return ""
    last = record.guidance_history[-1]
    response = last.get("response") if isinstance(last, dict) else None
    if isinstance(response, dict):
        if response.get("text"):
            return str(response["text"])
        if response.get("choice_id"):
            return str(response["choice_id"])
        if response.get("structured"):
            return json.dumps(response["structured"])
    return json.dumps(last)


__all__ = [
    "GeneratorLocalWork",
    "NoOpGeneratorLocalWork",
    "ProjectCodingLocalWork",
]
