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
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
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


class PlanClassifyLocalWork(GeneratorLocalWork):
    """Classify / refine instruction plans without a coding tool loop.

    Offline story path: runs ``build_instruction_plan``, returns
    ``request_guidance`` when refinement is needed, otherwise completes with
    ``mode`` / ``plan`` payload. No Completer or workspace tools.
    """

    def run(self, record: GeneratorRunRecord) -> dict[str, Any]:
        if record.recipe_id not in _PLAN_RECIPES:
            return {"result": "ok", "skipped": True, "recipe_id": record.recipe_id}
        try:
            built = build_instruction_plan(
                dict(record.inputs or {}),
                guidance_history=list(record.guidance_history),
            )
        except Exception as exc:  # noqa: BLE001 - surface into failed payload
            return {"result": "failed", "error": str(exc)}
        if built.guidance:
            return {
                "result": "needs_guidance",
                "request_guidance": guidance_asks_to_payloads(built.guidance),
                "plan_phase": "refine",
            }
        plan = built.plan
        if plan is None:
            return {"result": "failed", "error": "instruction_plan_empty"}
        return {
            "result": "ok",
            "mode": plan.mode,
            "plan": _plan_payload(plan),
            "guidance": _latest_guidance_text(record),
        }


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
        workspace_root: str | Path | None = None,
        event_log: Any | None = None,
    ) -> None:
        self._tools = tools
        self._complete = complete
        self._max_iterations = max_iterations
        self._workspace_root = (
            str(Path(workspace_root).expanduser().resolve())
            if workspace_root is not None
            else None
        )
        self._event_log = event_log
        self._written_files: list[str] = []

    def bind_event_log(self, event_log: Any) -> None:
        """Share the host/CLI EventLog so coding graph emits are observable."""
        self._event_log = event_log

    def run(self, record: GeneratorRunRecord) -> dict[str, Any]:
        if record.recipe_id not in _PLAN_RECIPES:
            return {"result": "ok", "skipped": True, "recipe_id": record.recipe_id}
        try:
            return self._run_sync(record)
        except Exception as exc:  # noqa: BLE001 - surface into completed/failed payload
            return {"result": "failed", "error": str(exc)}

    def _run_sync(self, record: GeneratorRunRecord) -> dict[str, Any]:
        """Drive ``_run_async`` from sync callers (CLI / durable / stories).

        ``asyncio.run`` cannot nest inside a running loop (async story harness,
        MCP). Fall back to a worker thread in that case.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._run_async(record))
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(self._run_async(record))).result()

    def _artifact_fields(self) -> dict[str, Any]:
        out: dict[str, Any] = {"written_files": list(self._written_files)}
        if self._workspace_root is not None:
            out["workspace_root"] = self._workspace_root
        return out

    def _note_write(self, path: str) -> None:
        rel = str(path).strip().replace("\\", "/")
        if rel and rel not in self._written_files:
            self._written_files.append(rel)

    async def _run_async(self, record: GeneratorRunRecord) -> dict[str, Any]:
        self._written_files = []
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
                **self._artifact_fields(),
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
                    **self._artifact_fields(),
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
                    **self._artifact_fields(),
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
                **self._artifact_fields(),
            }

        verify_runs = _normalize_verify_runs(inputs.get("verify_runs"))
        verify_failures = self._execute_verify_runs(verify_runs)
        repair_rounds = 0
        max_repair_rounds = 2
        while (
            verify_failures
            and "write_file" in self._tools
            and repair_rounds < max_repair_rounds
        ):
            repair_rounds += 1
            repair_goal = (
                "Verify / acceptance checks failed after your edits. Treat this as "
                "refinement round "
                f"{repair_rounds}/{max_repair_rounds}: restore the required public "
                "API (named def evaluate / def main when required), forbid eval/exec "
                "on user input, and make every listed check pass. Then call "
                "write_file with the full updated file(s).\n"
                + "\n".join(verify_failures)
            )
            repair_item = TodoItem(
                id=f"verify_repair_{repair_rounds}",
                instruction=repair_goal,
                acceptance=[],
            )
            repair_out = await self._run_item(
                record,
                plan,
                repair_item,
                work_item_index=len(plan.items) + repair_rounds,
                path_prefix=prefix,
            )
            item_results.append({**repair_out, "item_id": repair_item.id})
            if repair_out.get("result") == "failed":
                return {
                    **repair_out,
                    "plan": _plan_payload(plan),
                    "item_results": item_results,
                    "verify_failures": verify_failures,
                    "error": (
                        f"{repair_out.get('error') or 'repair_failed'}; "
                        + "; ".join(verify_failures)
                    ),
                    **self._artifact_fields(),
                }
            verify_failures = self._execute_verify_runs(verify_runs)
        if verify_failures:
            return {
                "result": "failed",
                "error": "verify_runs_failed: " + "; ".join(verify_failures),
                "verify_failures": verify_failures,
                "plan": _plan_payload(plan),
                "item_results": item_results,
                **self._artifact_fields(),
            }

        return {
            "result": "ok",
            "mode": plan.mode,
            "plan": _plan_payload(plan),
            "item_results": item_results,
            "guidance": _latest_guidance_text(record),
            "verify_runs": len(verify_runs),
            **self._artifact_fields(),
        }

    def _execute_verify_runs(
        self, verify_runs: list[dict[str, Any]]
    ) -> list[str]:
        """Run host-side workspace checks; return human-readable failure lines.

        Spec keys:

        - ``path``: workspace-relative file (required for text / python checks)
        - ``text_contains`` / ``text_forbids``: str or list[str] file text gates
        - ``min_bytes``: refuse if file is shorter than this many UTF-8 bytes
        - ``python_parses``: truthy → ``ast.parse`` must succeed
        - ``args`` / ``stdout_contains`` / ``exit_code``: ``python path …args``
        - ``pytest``: truthy → run ``python -m pytest -q <path>`` (path may be
          a test file or directory). Optional ``args`` append after ``-q``.
        - ``ruff``: truthy → run ``python -m ruff check <path|.>`` (static lint).
        - ``mypy``: truthy → run ``python -m mypy <path|.>`` (static types).
        """
        if not verify_runs:
            return []
        if self._workspace_root is None:
            return ["verify_runs require workspace_root"]
        root = Path(self._workspace_root)
        failures: list[str] = []
        for index, spec in enumerate(verify_runs):
            path = str(spec.get("path") or "").strip()
            use_pytest = bool(spec.get("pytest"))
            use_ruff = bool(spec.get("ruff"))
            use_mypy = bool(spec.get("mypy"))
            if not path and not (use_pytest or use_ruff or use_mypy):
                failures.append(f"verify_runs[{index}]: missing path")
                continue
            target = root / path if path else root
            text_needles = _as_str_list(spec.get("text_contains"))
            text_forbids = _as_str_list(spec.get("text_forbids"))
            min_bytes = spec.get("min_bytes")
            python_parses = bool(spec.get("python_parses"))
            needs_body = bool(
                text_needles or text_forbids or min_bytes is not None or python_parses
            )
            body = ""
            if needs_body:
                if not target.is_file():
                    failures.append(f"verify_runs[{index}]: missing file {path}")
                    continue
                try:
                    body = target.read_text(encoding="utf-8")
                except OSError as exc:
                    failures.append(f"verify_runs[{index}] {path}: read failed: {exc}")
                    continue
                if min_bytes is not None:
                    size = len(body.encode("utf-8"))
                    floor = int(min_bytes)
                    if size < floor:
                        failures.append(
                            f"verify_runs[{index}] {path}: file too small "
                            f"({size} < {floor} bytes) — possible gutting"
                        )
                if python_parses:
                    import ast

                    try:
                        ast.parse(body, filename=path)
                    except SyntaxError as exc:
                        failures.append(
                            f"verify_runs[{index}] {path}: python_parses "
                            f"failed: {exc}"
                        )
                for text_needle in text_needles:
                    if text_needle not in body:
                        failures.append(
                            f"verify_runs[{index}] {path}: expected file text to "
                            f"contain {text_needle!r}"
                        )
                for banned in text_forbids:
                    if banned in body:
                        failures.append(
                            f"verify_runs[{index}] {path}: file text must not "
                            f"contain {banned!r}"
                        )
            if use_pytest or use_ruff or use_mypy:
                if path and not target.exists():
                    tool = (
                        "pytest" if use_pytest else ("ruff" if use_ruff else "mypy")
                    )
                    failures.append(
                        f"verify_runs[{index}]: missing {tool} path {path}"
                    )
                    continue
                extra = [str(a) for a in list(spec.get("args") or [])]
                if use_pytest:
                    cmd = [sys.executable, "-m", "pytest", "-q"]
                    if path:
                        cmd.append(path)
                    tool_label = "pytest"
                    timeout_default = 60.0
                elif use_ruff:
                    cmd = [sys.executable, "-m", "ruff", "check"]
                    cmd.append(path if path else ".")
                    tool_label = "ruff"
                    timeout_default = 60.0
                else:
                    # Match CI-shaped strictness for isolated story workspaces
                    # that lack a pyproject mypy stanza.
                    cmd = [sys.executable, "-m", "mypy"]
                    cmd.append(path if path else ".")
                    has_flag = any(
                        str(a).startswith("-") for a in list(spec.get("args") or [])
                    )
                    has_config = (root / "mypy.ini").is_file() or (
                        root / "pyproject.toml"
                    ).is_file()
                    if not has_flag and not has_config:
                        cmd.append("--disallow-untyped-defs")
                    tool_label = "mypy"
                    timeout_default = 120.0
                cmd.extend(extra)
                expected_exit = int(spec.get("exit_code", 0))
                try:
                    completed = subprocess.run(
                        cmd,
                        cwd=str(root),
                        capture_output=True,
                        text=True,
                        timeout=float(
                            spec.get("timeout_seconds") or timeout_default
                        ),
                        check=False,
                    )
                except Exception as exc:  # noqa: BLE001
                    failures.append(
                        f"verify_runs[{index}] {tool_label} {path}: {exc}"
                    )
                    continue
                if int(completed.returncode) != expected_exit:
                    failures.append(
                        f"verify_runs[{index}] {tool_label} {path}: exit "
                        f"{completed.returncode} != {expected_exit}; "
                        f"stdout={completed.stdout.strip()!r}; "
                        f"stderr={completed.stderr.strip()!r}"
                    )
                continue
            # Process check only when the row asks for argv / stdout / exit.
            run_process = (
                "args" in spec
                or spec.get("stdout_contains") is not None
                or "exit_code" in spec
            )
            if not run_process:
                continue
            if not target.is_file():
                failures.append(f"verify_runs[{index}]: missing file {path}")
                continue
            args = [str(a) for a in list(spec.get("args") or [])]
            expected_exit = int(spec.get("exit_code", 0))
            stdout_needle = spec.get("stdout_contains")
            try:
                completed = subprocess.run(
                    [sys.executable, str(target), *args],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=float(spec.get("timeout_seconds") or 30),
                    check=False,
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"verify_runs[{index}] {path} {args}: {exc}")
                continue
            if int(completed.returncode) != expected_exit:
                failures.append(
                    f"verify_runs[{index}] {path} {args}: exit "
                    f"{completed.returncode} != {expected_exit}; "
                    f"stderr={completed.stderr.strip()!r}"
                )
                continue
            if (
                stdout_needle is not None
                and str(stdout_needle) not in (completed.stdout or "")
            ):
                failures.append(
                    f"verify_runs[{index}] {path} {args}: expected stdout to "
                    f"contain {stdout_needle!r}, got {completed.stdout!r}"
                )
        return failures

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
            verify_hint = ""
            verify_runs = _normalize_verify_runs(
                (record.inputs or {}).get("verify_runs")
            )
            if verify_runs and not str(item.id).startswith("verify_repair"):
                lines = []
                for spec in verify_runs:
                    path = spec.get("path")
                    for needle in _as_str_list(spec.get("text_contains")):
                        lines.append(f"  - {path} must contain {needle!r}")
                    for banned in _as_str_list(spec.get("text_forbids")):
                        lines.append(f"  - {path} must NOT contain {banned!r}")
                    if spec.get("pytest"):
                        lines.append(f"  - pytest -q {path} must exit 0")
                    elif spec.get("ruff"):
                        lines.append(
                            f"  - ruff check {path or '.'} must exit 0"
                        )
                    elif spec.get("mypy"):
                        lines.append(f"  - mypy {path or '.'} must exit 0")
                    elif (
                        "args" in spec
                        or spec.get("stdout_contains") is not None
                        or "exit_code" in spec
                    ):
                        args = " ".join(str(a) for a in list(spec.get("args") or []))
                        out_n = spec.get("stdout_contains")
                        lines.append(
                            f"  - python {path} {args} → stdout contains {out_n!r}"
                        )
                if lines:
                    verify_hint = (
                        "\nHost will verify after you finish:\n"
                        + "\n".join(lines)
                        + "\n"
                    )
            messages = [
                {
                    "role": "user",
                    "content": (
                        f"Plan mode: {plan.mode}\n"
                        f"Todo {item.id}: {goal}\n"
                        f"Item acceptance: {item.acceptance}\n"
                        f"Driver guidance: {guidance_text}\n"
                        f"{verify_hint}"
                        "Use tools to implement this item under the workspace. "
                        "Prefer run_shell to self-check before finishing."
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
            if name == "write_file" and isinstance(arguments, dict):
                path = arguments.get("path")
                if path is not None:
                    self._note_write(str(path))
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
        executor = host_graph_executor(
            runners=[loop_runner],
            grants=grants,
            event_log=self._event_log,
        )
        writes_before = len(self._written_files)
        result = await executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            envelope=CapabilityEnvelope.from_grants(grants),
            run_id=f"local:{record.run_id}:{item.id}",
            skip_linkage=True,
        )
        tools_out = graph.nodes["tools"].payload or {}
        # Live models sometimes summarize without write_file; one recovery burst.
        if (
            result.status == "ok"
            and len(self._written_files) == writes_before
            and _instruction_expects_write(goal)
            and "write_file" in self._tools
        ):
            recovery_messages = list(tools_out.get("messages") or messages)
            recovery_messages.append(
                {
                    "role": "user",
                    "content": (
                        "You finished without calling write_file. "
                        "Call write_file now with the full updated file contents "
                        "for this todo, then stop with a short summary."
                    ),
                }
            )
            recover_iters = min(8, max(2, max_iterations // 2))
            recover_graph = ConversationalToolLoopTemplate().instantiate(
                GraphTemplateParams(
                    goal=goal,
                    inputs={
                        "max_iterations": recover_iters,
                        "messages": recovery_messages,
                    },
                    soft_bindings={"max_iterations": recover_iters},
                )
            )
            recover_node = recover_graph.nodes["tools"]
            recover_node.repeating = False
            recover_node.payload = {
                **dict(recover_node.payload or {}),
                "messages": recovery_messages,
                "max_iterations": recover_iters,
            }
            recover_result = await executor.run(
                recover_graph,
                budget_policy=BudgetPolicy.unlimited(),
                envelope=CapabilityEnvelope.from_grants(grants),
                run_id=f"local:{record.run_id}:{item.id}:write_recover",
                skip_linkage=True,
            )
            recover_out = recover_graph.nodes["tools"].payload or {}
            tools_out = {
                **tools_out,
                "rounds": int(tools_out.get("rounds") or 0)
                + int(recover_out.get("rounds") or 0),
                "final_text": recover_out.get("final_text")
                or tools_out.get("final_text"),
                "write_recovered": True,
            }
            if recover_result.status != "ok":
                result = recover_result
        return {
            "result": "ok" if result.status == "ok" else "failed",
            "graph_status": result.status,
            "goal": goal,
            "rounds": tools_out.get("rounds"),
            "final_text": tools_out.get("final_text"),
            "error": result.error,
            "write_recovered": bool(tools_out.get("write_recovered")),
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


def _normalize_verify_runs(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("path"):
            out.append(dict(item))
    return out


def _as_str_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x)]
    return [str(raw)]


def _instruction_expects_write(instruction: str) -> bool:
    """Heuristic: coding todos that create/update files should call write_file."""
    text = instruction.lower()
    markers = (
        "write",
        "update",
        "create",
        "edit",
        "implement",
        "extend",
        "add ",
        "fix",
        ".py",
        "calc.py",
    )
    return any(marker in text for marker in markers)


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
    "PlanClassifyLocalWork",
    "ProjectCodingLocalWork",
]
