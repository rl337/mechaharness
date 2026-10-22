"""Local work hook for :class:`~mechaharness.durable_graph_generator.DurableGraphGenerator`.

Between guidance yields (DG-13), the generator may run token-heavy work via an
injectable hook. Default is a no-op so offline stories stay model-free.
``ProjectCodingConfig`` binds a coding burst that expands a conversational
tool loop with workspace tools, optionally after building an
``instruction_todo_plan`` (oneshot vs list + acceptance + refinement).
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
from mechaharness.instruction_plan import (
    InstructionPlan,
    TodoItem,
    build_instruction_plan,
    guidance_asks_to_payloads,
    verify_acceptance,
)
from mechaharness.mcp_progress import (
    coding_progress_prefix,
    get_mcp_progress,
    report_mcp_progress,
)
from mechaharness.tools.base import ToolRegistry

_PLAN_RECIPES = frozenset(
    {"guided_coding", "conversational_tool_loop", "instruction_todo_plan"}
)


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
    """Run instruction-plan stages then conversational tool-loop bursts.

    Used after ``guided_coding`` / ``instruction_todo_plan`` guidance is
    answered. When the plan needs human calling refinement, returns
    ``request_guidance`` so the generator yields and restarts with answers.
    ``complete`` returns an assistant-shaped dict (optionally with OpenAI-style
    ``tool_calls``).
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
        if record.recipe_id not in _PLAN_RECIPES:
            return {"result": "ok", "skipped": True, "recipe_id": record.recipe_id}
        try:
            return asyncio.run(self._run_async(record))
        except Exception as exc:  # noqa: BLE001 - surface into completed/failed payload
            return {"result": "failed", "error": str(exc)}

    async def _run_async(self, record: GeneratorRunRecord) -> dict[str, Any]:
        inputs = dict(record.inputs or {})
        built = build_instruction_plan(
            inputs, guidance_history=list(record.guidance_history)
        )
        if built.guidance:
            return {
                "result": "needs_guidance",
                "request_guidance": guidance_asks_to_payloads(built.guidance),
                "plan_phase": "refine",
            }
        plan = built.plan
        if plan is None:
            return {"result": "failed", "error": "instruction_plan_empty"}

        # Pre-list acceptance: explicit checks or soft pass when criteria empty.
        pre_checks = _acceptance_checks(inputs, "pre_acceptance_checks")
        pre_ok, pre_fail = verify_acceptance(
            plan.pre_acceptance,
            evidence=_latest_guidance_text(record) or str(inputs.get("goal") or ""),
            checks=pre_checks,
        )
        if plan.pre_acceptance and not pre_ok and pre_checks:
            return {
                "result": "failed",
                "error": "pre_acceptance_failed",
                "failures": pre_fail,
                "plan": _plan_payload(plan),
            }

        item_results: list[dict[str, Any]] = []
        prefix = coding_progress_prefix(record.recipe_id)
        progress = get_mcp_progress()
        if progress is not None:
            progress.base_segments = list(prefix)
            progress.report("plan")
        for item_index, item in enumerate(plan.items, start=1):
            report_mcp_progress(f"work_item {item_index}")
            item_out = await self._run_item(
                record, plan, item, work_item_index=item_index, path_prefix=prefix
            )
            if item_out.get("result") == "failed":
                return {
                    **item_out,
                    "plan": _plan_payload(plan),
                    "item_results": item_results,
                }
            item_checks = _acceptance_checks(
                inputs, "item_acceptance_checks", item_id=item.id
            )
            # Offline stubs often omit criterion text; treat non-empty final_text
            # plus explicit true checks as evidence.
            evidence = str(item_out.get("final_text") or item.instruction)
            ok, failures = verify_acceptance(
                item.acceptance, evidence=evidence, checks=item_checks
            )
            if item.acceptance and item_checks and not ok:
                return {
                    "result": "failed",
                    "error": "item_acceptance_failed",
                    "item_id": item.id,
                    "failures": failures,
                    "plan": _plan_payload(plan),
                    "item_results": item_results + [item_out],
                }
            item_results.append({**item_out, "item_id": item.id, "accepted": True})

        post_checks = _acceptance_checks(inputs, "post_acceptance_checks")
        post_evidence = "\n".join(
            str(r.get("final_text") or "") for r in item_results
        )
        post_ok, post_fail = verify_acceptance(
            plan.post_acceptance, evidence=post_evidence, checks=post_checks
        )
        if plan.post_acceptance and post_checks and not post_ok:
            return {
                "result": "failed",
                "error": "post_acceptance_failed",
                "failures": post_fail,
                "plan": _plan_payload(plan),
                "item_results": item_results,
            }

        return {
            "result": "ok",
            "mode": plan.mode,
            "plan": _plan_payload(plan),
            "item_results": item_results,
            "guidance": _latest_guidance_text(record),
        }

    async def _run_item(
        self,
        record: GeneratorRunRecord,
        plan: InstructionPlan,
        item: TodoItem,
        *,
        work_item_index: int = 1,
        path_prefix: list[str] | None = None,
    ) -> dict[str, Any]:
        guidance_text = _latest_guidance_text(record)
        goal = item.instruction
        messages = list((record.inputs or {}).get("messages") or [])
        if not messages:
            messages = [
                {
                    "role": "user",
                    "content": (
                        f"Plan mode: {plan.mode}\n"
                        f"Todo {item.id}: {goal}\n"
                        f"Item acceptance: {item.acceptance}\n"
                        f"Driver guidance: {guidance_text}\n"
                        "Use tools to implement this item under the workspace."
                    ),
                }
            ]
        else:
            # Append item context so multi-item runs stay distinct.
            messages = [
                *messages,
                {
                    "role": "user",
                    "content": f"Next todo {item.id}: {goal}",
                },
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

        root = list(path_prefix or coding_progress_prefix(record.recipe_id))
        work_seg = f"work_item {work_item_index}"

        def on_progress(
            *,
            tool_round: int,
            phase: str | None = None,
            tool: str | None = None,
        ) -> None:
            round_seg = f"tool_round {tool_round}"
            if tool is not None:
                report_mcp_progress(work_seg, round_seg, str(tool))
            else:
                report_mcp_progress(work_seg, round_seg, str(phase or "inference"))

        # Keep sticky base as recipe (+ plan_tile); work_item is per report.
        progress = get_mcp_progress()
        if progress is not None:
            progress.base_segments = list(root)

        loop_runner = ConversationalToolLoopRunner(
            complete=self._complete,
            dispatch_tool=dispatch_tool,
            on_progress=on_progress,
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
        # Looping is owned by ConversationalToolLoopRunner; outer repeating
        # would leave the graph incomplete after an interior success.
        tools_node.repeating = False
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
            run_id=f"local:{record.run_id}:{item.id}",
            skip_linkage=True,
        )
        tools_out = graph.nodes["tools"].payload or {}
        return {
            "result": "ok" if result.status == "ok" else "failed",
            "graph_status": result.status,
            "goal": goal,
            "rounds": tools_out.get("rounds"),
            "final_text": tools_out.get("final_text"),
            "error": result.error,
        }


def _plan_payload(plan: InstructionPlan) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "refined": plan.refined,
        "conflicts": list(plan.conflicts),
        "pre_acceptance": list(plan.pre_acceptance),
        "post_acceptance": list(plan.post_acceptance),
        "items": [
            {
                "id": it.id,
                "instruction": it.instruction,
                "acceptance": list(it.acceptance),
            }
            for it in plan.items
        ],
    }


def _acceptance_checks(
    inputs: dict[str, Any],
    key: str,
    *,
    item_id: str | None = None,
) -> dict[str, bool]:
    raw = inputs.get(key)
    if item_id and isinstance(inputs.get("item_acceptance_checks"), dict):
        nested = inputs["item_acceptance_checks"].get(item_id)
        if isinstance(nested, dict):
            raw = nested
    if not isinstance(raw, dict):
        return {}
    return {str(k): bool(v) for k, v in raw.items()}


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
