"""Project coding host Config — dogfood MCP / local openai_local coding.

``ProjectCodingConfig`` roots tools at ``MECHA_WORKSPACE`` (or cwd), registers
workspace coding tools, prefers ``openai_local`` from Settings / MCP ``env``,
and binds :class:`~mechaharness.generator_local_work.ProjectCodingLocalWork`
so ``guided_coding`` / ``instruction_todo_plan`` runs perform tool-loop bursts
after guidance (oneshot or todo list with acceptance).
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any

from pyiv.files import Filesystem, RealFilesystem

from mechaharness.config import Settings
from mechaharness.core.access import (
    FsRead,
    FsWrite,
    GraphEscalate,
    GraphExecute,
    ProcessExec,
)
from mechaharness.di import SettingsConfig, apply_backend_defaults
from mechaharness.generator_local_work import (
    GeneratorLocalWork,
    ProjectCodingLocalWork,
)
from mechaharness.graph_templates.catalog import default_graph_template_classes
from mechaharness.graph_templates.guided_coding import GuidedCodingTemplate
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.base import Completer, InferenceStrategy
from mechaharness.project_coding_tools import (
    WorkspacePaths,
    build_coding_tool_registry,
    resolve_workspace_root,
)
from mechaharness.tools.base import ToolRegistry


def _settings_for_project_coding() -> Settings:
    """Load Settings from process env (MCP ``env`` primary) + optional cwd ``.env``."""
    raw = Settings()
    if raw.base_url and not os.environ.get("MECHA_INFERENCE_BACKEND"):
        if raw.inference_backend in {"openai"}:
            raw = raw.model_copy(update={"inference_backend": "openai_local"})
    return apply_backend_defaults(raw)


class ProjectCodingConfig(SettingsConfig):
    """Host Config for project-rooted coding via MCP / durable generator."""

    def __init__(
        self,
        settings: Settings | None = None,
        tools: ToolRegistry | None = None,
        *,
        workspace: Path | str | None = None,
        filesystem: Filesystem | None = None,
        completer: Completer | None = None,
    ) -> None:
        self._workspace_root = resolve_workspace_root(workspace)
        self._filesystem_override = filesystem
        self._completer_override = completer
        resolved = settings if settings is not None else _settings_for_project_coding()
        if not os.environ.get("MECHA_HARNESS_FAMILY"):
            resolved = resolved.model_copy(update={"harness_family": "tool_loop"})
        super().__init__(settings=resolved, tools=tools)

    def get_filesystem(self) -> type[Filesystem] | Filesystem:
        if self._filesystem_override is not None:
            return self._filesystem_override
        return RealFilesystem

    def get_tools(self) -> ToolRegistry:
        if self._provided_tools is not None:
            return self._provided_tools
        fs = self._filesystem_override or RealFilesystem()
        return build_coding_tool_registry(
            workspace=WorkspacePaths(self._workspace_root),
            filesystem=fs,
        )

    def get_grants(self) -> list[object]:
        return [FsRead, FsWrite, ProcessExec, GraphExecute, GraphEscalate]

    def get_harness_class(self) -> type[AbstractHarness]:
        try:
            return super().get_harness_class()
        except KeyError:
            return ToolLoopHarness

    def graph_template_classes(self) -> dict[str, type]:
        classes = dict(default_graph_template_classes())
        classes[GuidedCodingTemplate.name] = GuidedCodingTemplate
        return classes

    def configure(self) -> None:
        super().configure()
        if self._completer_override is not None:
            self.register_instance(Completer, self._completer_override)
            if isinstance(self._completer_override, InferenceStrategy):
                self.register_instance(InferenceStrategy, self._completer_override)

        tools = self.get_tools()
        completer = self._completer_override
        max_turns = int(self.get_settings().max_turns or 8)

        def make_local_work(injector: Any) -> GeneratorLocalWork:
            complete = completer
            settings = injector.inject(Settings)
            if complete is None and settings.base_url:
                try:
                    complete = injector.inject(Completer)
                except Exception:  # noqa: BLE001
                    complete = None
            if complete is None:
                fn: Any = _offline_stub_complete(tools)
            else:
                fn = _as_complete_fn(complete)
            return ProjectCodingLocalWork(
                tools=tools,
                complete=fn,
                max_iterations=max_turns,
            )

        # Replace default NoOp with coding burst (last register wins).
        self.register(GeneratorLocalWork, make_local_work, singleton=True)


def _as_complete_fn(completer: Any) -> Any:
    """Adapt Completer / callable into ConversationalToolLoopRunner complete.

    May return an awaitable; the tool-loop runner awaits it.
    """

    if callable(completer) and not hasattr(completer, "complete"):
        return completer

    def complete(messages: list[dict[str, Any]], meta: Any) -> Any:
        del meta
        if not hasattr(completer, "complete"):
            return {"role": "assistant", "content": str(completer), "tool_calls": []}
        result = completer.complete(messages)
        if inspect.isawaitable(result):
            return _awaitable_to_assistant(result)
        return _normalize_assistant(result)

    return complete


async def _awaitable_to_assistant(result: Any) -> dict[str, Any]:
    return _normalize_assistant(await result)


def _normalize_assistant(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    content = getattr(result, "content", None)
    if content is None and hasattr(result, "message"):
        content = getattr(result.message, "content", None)
    tool_calls = getattr(result, "tool_calls", None) or []
    # OpenAI CompletionResponse shape
    if hasattr(result, "message") and getattr(result.message, "tool_calls", None):
        tool_calls = result.message.tool_calls
    return {
        "role": "assistant",
        "content": content if content is not None else str(result),
        "tool_calls": list(tool_calls),
    }


def _offline_stub_complete(tools: ToolRegistry) -> Any:
    """Deterministic complete for tests when no Completer is bound."""

    state = {"wrote": False}

    def complete(messages: list[dict[str, Any]], meta: Any) -> dict[str, Any]:
        del messages, meta
        if not state["wrote"] and "write_file" in tools:
            state["wrote"] = True
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_write",
                        "function": {
                            "name": "write_file",
                            "arguments": {
                                "path": ".mechaharness/guided_coding_stub.txt",
                                "content": "guided_coding ok\n",
                            },
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "done", "tool_calls": []}

    return complete


def mcp_host_config_class() -> type[ProjectCodingConfig] | None:
    """Resolve MCP host Config from ``MECHA_MCP_HOST``.

    Unset / ``none`` / ``bare`` → registry-only generator (doctests, demos).
    ``project_coding`` → :class:`ProjectCodingConfig` (blessed Cursor MCP env).
    """
    raw = os.environ.get("MECHA_MCP_HOST")
    if raw is None or raw.strip() == "":
        return None
    name = raw.strip().lower()
    if name in {"none", "bare", "default", "0", "false"}:
        return None
    if name in {"project_coding", "coding", "1", "true"}:
        return ProjectCodingConfig
    raise KeyError(f"unknown MECHA_MCP_HOST={name!r}")


__all__ = [
    "ProjectCodingConfig",
    "mcp_host_config_class",
]
