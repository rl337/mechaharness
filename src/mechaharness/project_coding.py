"""Project coding host Config — dogfood MCP / local openai_local coding.

``ProjectCodingConfig`` roots tools at ``MECHA_WORKSPACE`` (or cwd), registers
workspace coding tools, prefers ``openai_local`` from Settings / MCP ``env``,
and binds :class:`~mechaharness.generator_local_work.ProjectCodingLocalWork`
so ``guided_coding`` / ``instruction_todo_plan`` runs perform tool-loop bursts
after guidance (oneshot or todo list with acceptance).
"""

from __future__ import annotations

import inspect
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from pyiv.files import Filesystem, RealFilesystem

from mechaharness.coding_git import (
    CodingGit,
    LocalGitHttpPullRequestCodingGit,
    LocalProcessCodingGit,
)
from mechaharness.config import Settings
from mechaharness.core.access import (
    FsRead,
    FsWrite,
    GraphEscalate,
    GraphExecute,
    ProcessExec,
)
from mechaharness.core.completer import Completer
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    ToolCall,
)
from mechaharness.di import SettingsConfig, apply_backend_defaults
from mechaharness.generator_local_work import (
    GeneratorLocalWork,
    ProjectCodingLocalWork,
)
from mechaharness.github_client import GitHubClient, HttpGitHubClient
from mechaharness.github_connection import GitHubConnectionConfig
from mechaharness.graph_templates.catalog import default_graph_template_classes
from mechaharness.graph_templates.guided_coding import GuidedCodingTemplate
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.project_coding_tools import (
    WorkspacePaths,
    build_coding_tool_registry,
    resolve_workspace_root,
)
from mechaharness.tools.base import ToolRegistry


def _settings_for_project_coding() -> Settings:
    """Load Settings from process env (MCP / ``.env/env.sh`` primary)."""
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
        coding_git: CodingGit | None = None,
        github_connection: GitHubConnectionConfig | None = None,
        github_client: GitHubClient | None = None,
    ) -> None:
        self._workspace_root = resolve_workspace_root(workspace)
        self._filesystem_override = filesystem
        self._completer_override = completer
        self._coding_git_override = coding_git
        self._github_connection_override = github_connection
        self._github_client_override = github_client
        resolved = settings if settings is not None else _settings_for_project_coding()
        if not os.environ.get("MECHA_HARNESS_FAMILY"):
            resolved = resolved.model_copy(update={"harness_family": "tool_loop"})
        super().__init__(settings=resolved, tools=tools)

    def get_filesystem(self) -> type[Filesystem] | Filesystem:
        if self._filesystem_override is not None:
            return self._filesystem_override
        return RealFilesystem

    def get_github_connection(
        self,
    ) -> GitHubConnectionConfig | type[GitHubConnectionConfig]:
        """GitHub HTTP reachability (token + API base). Not Settings."""
        if self._github_connection_override is not None:
            return self._github_connection_override
        return GitHubConnectionConfig

    def get_github_client(self) -> GitHubClient | type[GitHubClient] | None:
        """Forge client for HTTP pull requests. ``None`` → no HTTP PR binding."""
        if self._github_client_override is not None:
            return self._github_client_override
        conn = self._resolve_github_connection()
        if not conn.enabled():
            return None
        return HttpGitHubClient

    def get_coding_git(self) -> type[CodingGit] | CodingGit:
        """VCS/PR backend for coding tools (override for HTTPS / forge API)."""
        if self._coding_git_override is not None:
            return self._coding_git_override
        return LocalProcessCodingGit

    def _resolve_github_connection(self) -> GitHubConnectionConfig:
        bound = self.get_github_connection()
        if isinstance(bound, type):
            from pyiv.process import OsEnvironment

            return GitHubConnectionConfig.from_env(OsEnvironment())
        return bound

    def get_tools(self) -> ToolRegistry:
        if self._provided_tools is not None:
            return self._provided_tools
        # Early/default: local git (+ optional gh). configure() rebinds ToolRegistry
        # with LocalGitHttpPullRequestCodingGit when a GitHub token is present.
        fs = self._filesystem_override or RealFilesystem()
        coding_git = (
            self._coding_git_override
            if self._coding_git_override is not None
            else LocalProcessCodingGit(workspace=self._workspace_root)
        )
        return build_coding_tool_registry(
            workspace=WorkspacePaths(self._workspace_root),
            filesystem=fs,
            coding_git=coding_git,
            github=None,
            github_connection=None,
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

        connection = self._resolve_github_connection()
        self.register_instance(GitHubConnectionConfig, connection)

        client_binding = self.get_github_client()
        if isinstance(client_binding, GitHubClient):
            self.register_instance(GitHubClient, client_binding)
        elif client_binding is not None:

            def make_github(injector: Any) -> GitHubClient:
                from pyiv.http import AsyncHttpClient

                return HttpGitHubClient(
                    connection=injector.inject(GitHubConnectionConfig),
                    client=injector.inject(AsyncHttpClient),
                )

            self.register(GitHubClient, make_github, singleton=True)

        workspace = self._workspace_root

        def make_coding_git(injector: Any) -> CodingGit:
            if self._coding_git_override is not None:
                return self._coding_git_override
            conn = injector.inject(GitHubConnectionConfig)
            if conn.enabled():
                try:
                    github = injector.inject(GitHubClient)
                except Exception:  # noqa: BLE001
                    github = None
                if github is not None:
                    return LocalGitHttpPullRequestCodingGit(
                        workspace=workspace,
                        github=github,
                        connection=conn,
                    )
            return LocalProcessCodingGit(workspace=workspace)

        self.register(CodingGit, make_coding_git, singleton=True)

        if self._provided_tools is None:
            fs = self._filesystem_override or RealFilesystem()

            def make_tools(injector: Any) -> ToolRegistry:
                github = None
                conn = injector.inject(GitHubConnectionConfig)
                if conn.enabled():
                    try:
                        github = injector.inject(GitHubClient)
                    except Exception:  # noqa: BLE001
                        github = None
                return build_coding_tool_registry(
                    workspace=WorkspacePaths(workspace),
                    filesystem=fs,
                    coding_git=injector.inject(CodingGit),
                    github=github,
                    github_connection=conn,
                )

            self.register(ToolRegistry, make_tools, singleton=True)

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
            tool_reg = injector.inject(ToolRegistry)
            if complete is None:
                fn: Any = _offline_stub_complete(tool_reg)
            else:
                fn = _as_complete_fn(
                    complete,
                    tools=tool_reg,
                    model=str(settings.model or "local"),
                )
            return ProjectCodingLocalWork(
                tools=tool_reg,
                complete=fn,
                max_iterations=max_turns,
                workspace_root=workspace,
            )

        # Replace default NoOp with coding burst (last register wins).
        self.register(GeneratorLocalWork, make_local_work, singleton=True)


def _native_tools_enabled() -> bool:
    """OpenAI ``tools`` wire form needs vLLM ``--enable-auto-tool-choice``.

    Default is prompt-parsed tool calls so local openai_local dogfood works
    without that server flag. Set ``MECHA_NATIVE_TOOLS=1`` to send tools natively.
    """
    raw = (os.environ.get("MECHA_NATIVE_TOOLS") or "").strip().lower()
    return raw in {"1", "true", "yes", "native"}


def _as_complete_fn(
    completer: Any,
    *,
    tools: ToolRegistry,
    model: str,
    max_tokens: int | None = None,
) -> Any:
    """Adapt Completer / callable into ConversationalToolLoopRunner complete.

    Builds a :class:`CompletionRequest` so ``OpenAICompatStrategy.complete``
    receives domain types. By default tools are described in a system prompt
    and parsed from the assistant text (local vLLM without auto tool choice).
    """

    if callable(completer) and not hasattr(completer, "complete"):
        return completer

    tool_defs = tools.definitions()
    use_native = _native_tools_enabled()
    system_prompt = _prompt_tools_system(tool_defs)
    token_budget = max_tokens
    if token_budget is None:
        raw = (os.environ.get("MECHA_MAX_TOKENS") or "").strip()
        token_budget = int(raw) if raw.isdigit() else None

    def complete(messages: list[dict[str, Any]], meta: Any) -> Any:
        del meta
        if not hasattr(completer, "complete"):
            return {"role": "assistant", "content": str(completer), "tool_calls": []}
        if use_native:
            chat = _dicts_to_chat_messages(messages)
        else:
            chat = _messages_for_prompt_tools(messages, system_prompt)
        request = CompletionRequest(
            model=model,
            messages=chat,
            tools=list(tool_defs) if use_native else None,
            max_tokens=token_budget,
        )
        try:
            result = completer.complete(request)
            if inspect.isawaitable(result):
                return _awaitable_to_assistant(
                    result, parse_prompt_tools=not use_native
                )
            return _normalize_assistant(result, parse_prompt_tools=not use_native)
        except Exception as exc:  # noqa: BLE001 - keep tool loop from aborting mid-run
            return {
                "role": "assistant",
                "content": f"Inference error: {exc}. Stop and summarize.",
                "tool_calls": [],
            }

    return complete


async def _awaitable_to_assistant(
    result: Any, *, parse_prompt_tools: bool = False
) -> dict[str, Any]:
    try:
        return _normalize_assistant(await result, parse_prompt_tools=parse_prompt_tools)
    except Exception as exc:  # noqa: BLE001
        return {
            "role": "assistant",
            "content": f"Inference error: {exc}. Stop and summarize.",
            "tool_calls": [],
        }


def _prompt_tools_system(tool_defs: list[Any]) -> str:
    catalog = [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        }
        for t in tool_defs
    ]
    return (
        "You are a coding agent with workspace tools. "
        "To call a tool, emit one or more blocks exactly like:\n"
        "<tool_call>\n"
        '{"name": "TOOL_NAME", "arguments": {...}}\n'
        "</tool_call>\n"
        "You may call multiple tools by emitting multiple blocks. "
        "When creating or updating files you MUST call write_file with the full "
        "file contents before you finish — do not claim done without write_file. "
        "When finished (no more tools), reply with a short plain summary only.\n"
        "Thinking / reasoning models: keep internal reasoning short. Put every "
        "<tool_call>…</tool_call> block in the final answer content (not only in "
        "reasoning). Prefer one write_file of the full file over many tiny edits. "
        "Read existing files first; preserve prior behavior and APIs while adding "
        "the requested change (do not drop floats, operators, tests, or CLI entry "
        "points that already work).\n"
        "Scope discipline (implementation step): do not add speculative "
        "next-stage grammar, extra APIs, or drive-by refactors beyond the "
        "request. Extending is not replacing — keep every previously green "
        "host check working while you add what this todo / goal asks for. "
        "Leave truly unrequested next features for a later explicit step.\n"
        f"Available tools:\n{json.dumps(catalog, indent=2)}"
    )


def _messages_for_prompt_tools(
    wire_messages: list[dict[str, Any]], system_prompt: str
) -> list[ChatMessage]:
    """Build chat history for models without native tool-calling.

    ``role=tool`` becomes a user note; assistant tool_calls become ``<tool_call>``
    text so the transcript stays coherent across rounds.
    """
    out: list[ChatMessage] = [ChatMessage(role=Role.SYSTEM, content=system_prompt)]
    for raw in wire_messages:
        if not isinstance(raw, dict):
            continue
        role_raw = str(raw.get("role") or "user").lower()
        content = raw.get("content")
        if role_raw == "system":
            continue
        if role_raw == "tool":
            out.append(
                ChatMessage(
                    role=Role.USER,
                    content=(
                        f"Tool result for {raw.get('tool_call_id') or 'call'}:\n"
                        f"{'' if content is None else content}"
                    ),
                )
            )
            continue
        if role_raw == "assistant":
            text = "" if content is None else str(content)
            parsed_calls = _wire_tool_calls_to_domain(raw.get("tool_calls"))
            if parsed_calls:
                blocks = [
                    "<tool_call>\n"
                    + json.dumps({"name": tc.name, "arguments": tc.arguments})
                    + "\n</tool_call>"
                    for tc in parsed_calls
                ]
                text = (text + "\n" if text else "") + "\n".join(blocks)
            out.append(ChatMessage(role=Role.ASSISTANT, content=text or None))
            continue
        out.append(
            ChatMessage(
                role=Role.USER,
                content=None if content is None else str(content),
            )
        )
    return out


_TOOL_CALL_OPEN = re.compile(r"<tool_call\b[^>]*>", re.IGNORECASE)
_TOOL_CALL_CLOSE = re.compile(r"</tool_call\s*>", re.IGNORECASE)


def _extract_balanced_json_object(text: str, start: int) -> tuple[str | None, int]:
    """Return JSON object starting at *start* and the index after it."""
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        return None, start
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1], index + 1
    return None, start


def _parse_prompt_tool_calls(content: str | None) -> list[dict[str, Any]]:
    if not content:
        return []
    calls: list[dict[str, Any]] = []
    search_from = 0
    while True:
        open_match = _TOOL_CALL_OPEN.search(content, search_from)
        if open_match is None:
            break
        close_match = _TOOL_CALL_CLOSE.search(content, open_match.end())
        if close_match is None:
            # Truncated block — try balanced JSON anyway.
            payload_text, _ = _extract_balanced_json_object(content, open_match.end())
            search_from = open_match.end()
        else:
            inner = content[open_match.end() : close_match.start()]
            payload_text, _ = _extract_balanced_json_object(inner, 0)
            if payload_text is None:
                payload_text = inner.strip() or None
            search_from = close_match.end()
        if not payload_text:
            continue
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name") or "").strip()
        args = payload.get("arguments")
        if not name:
            continue
        if not isinstance(args, dict):
            args = {}
        calls.append(
            {
                "id": f"call_{uuid.uuid4().hex[:10]}",
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        )
    if calls:
        return calls
    # Fallback: single JSON object with name/arguments in the message.
    stripped = content.strip()
    if stripped.startswith("{") and '"name"' in stripped:
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and payload.get("name"):
            args = payload.get("arguments")
            if not isinstance(args, dict):
                args = {}
            return [
                {
                    "id": f"call_{uuid.uuid4().hex[:10]}",
                    "type": "function",
                    "function": {
                        "name": str(payload["name"]),
                        "arguments": args,
                    },
                }
            ]
    return calls


def _looks_like_broken_tool_call(content: str | None) -> bool:
    """True when the model attempted a prompt tool call that did not parse."""
    if not content:
        return False
    if _TOOL_CALL_OPEN.search(content) is None:
        return False
    return not _parse_prompt_tool_calls(content)


def _dicts_to_chat_messages(messages: list[dict[str, Any]]) -> list[ChatMessage]:
    """Convert tool-loop wire dicts into domain :class:`ChatMessage` values."""
    out: list[ChatMessage] = []
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        role_raw = str(raw.get("role") or "user").lower()
        try:
            role = Role(role_raw)
        except ValueError:
            role = Role.USER
        tool_calls = _wire_tool_calls_to_domain(raw.get("tool_calls"))
        content = raw.get("content")
        out.append(
            ChatMessage(
                role=role,
                content=None if content is None else str(content),
                name=raw.get("name"),
                tool_call_id=raw.get("tool_call_id"),
                tool_calls=tool_calls,
            )
        )
    return out


def _wire_tool_calls_to_domain(raw: Any) -> list[ToolCall] | None:
    if not isinstance(raw, list) or not raw:
        return None
    calls: list[ToolCall] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("function"), dict):
            fn = item["function"]
            name = str(fn.get("name") or "tool")
            args = fn.get("arguments")
        else:
            name = str(item.get("name") or "tool")
            args = item.get("arguments")
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
                args = parsed if isinstance(parsed, dict) else {"raw": args}
            except json.JSONDecodeError:
                args = {"raw": args}
        if not isinstance(args, dict):
            args = {}
        calls.append(
            ToolCall(
                id=str(item.get("id") or name),
                name=name,
                arguments=args,
            )
        )
    return calls or None


def _text_for_prompt_tool_parse(
    content: str | None, reasoning: str | None = None
) -> str | None:
    """Prefer assistant content; fall back to reasoning for thinking models."""
    chunks: list[str] = []
    if isinstance(content, str) and content.strip():
        chunks.append(content)
    if isinstance(reasoning, str) and reasoning.strip():
        chunks.append(reasoning)
    if not chunks:
        return content if isinstance(content, str) else None
    return "\n".join(chunks)


def _normalize_assistant(
    result: Any, *, parse_prompt_tools: bool = False
) -> dict[str, Any]:
    """Map Completer / CompletionResponse into OpenAI-style assistant dict."""
    if isinstance(result, dict):
        calls = result.get("tool_calls")
        content = result.get("content")
        reasoning = result.get("reasoning_content") or result.get("reasoning")
        if isinstance(reasoning, dict):
            reasoning = reasoning.get("content") or reasoning.get("text")
        if calls and isinstance(calls, list):
            wired = _domain_tool_calls_to_wire(calls)
        elif parse_prompt_tools:
            wired = _parse_prompt_tool_calls(
                _text_for_prompt_tool_parse(
                    content if isinstance(content, str) else None,
                    reasoning if isinstance(reasoning, str) else None,
                )
            )
        else:
            wired = []
        # Surface tool_call text into content when the model only reasoned.
        out_content = content
        if (
            parse_prompt_tools
            and wired
            and (not isinstance(out_content, str) or not out_content.strip())
            and isinstance(reasoning, str)
            and "<tool_call" in reasoning.lower()
        ):
            out_content = reasoning
        return {
            **result,
            "role": result.get("role") or "assistant",
            "content": out_content,
            "tool_calls": wired,
        }
    if isinstance(result, CompletionResponse):
        msg = result.message
        wired = _domain_tool_calls_to_wire(msg.tool_calls or [])
        reasoning = getattr(msg, "reasoning_content", None)
        if parse_prompt_tools and not wired:
            wired = _parse_prompt_tool_calls(
                _text_for_prompt_tool_parse(msg.content, reasoning)
            )
        out_content = msg.content
        if (
            parse_prompt_tools
            and wired
            and (not isinstance(out_content, str) or not out_content.strip())
            and isinstance(reasoning, str)
            and "<tool_call" in reasoning.lower()
        ):
            out_content = reasoning
        return {
            "role": "assistant",
            "content": out_content,
            "tool_calls": wired,
        }
    content = getattr(result, "content", None)
    if content is None and hasattr(result, "message"):
        content = getattr(result.message, "content", None)
    reasoning = getattr(result, "reasoning_content", None)
    if reasoning is None and hasattr(result, "message"):
        reasoning = getattr(result.message, "reasoning_content", None)
    tool_calls = getattr(result, "tool_calls", None) or []
    if hasattr(result, "message") and getattr(result.message, "tool_calls", None):
        tool_calls = result.message.tool_calls
    wired = _domain_tool_calls_to_wire(tool_calls)
    if parse_prompt_tools and not wired:
        wired = _parse_prompt_tool_calls(
            _text_for_prompt_tool_parse(
                content if isinstance(content, str) else None,
                reasoning if isinstance(reasoning, str) else None,
            )
        )
    out_content = content if content is not None else str(result)
    if (
        parse_prompt_tools
        and wired
        and (not isinstance(out_content, str) or not str(out_content).strip())
        and isinstance(reasoning, str)
        and "<tool_call" in reasoning.lower()
    ):
        out_content = reasoning
    return {
        "role": "assistant",
        "content": out_content,
        "tool_calls": wired,
    }


def _domain_tool_calls_to_wire(calls: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not calls:
        return out
    for call in calls:
        if isinstance(call, ToolCall):
            out.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
            )
            continue
        if isinstance(call, dict):
            if isinstance(call.get("function"), dict):
                out.append(call)
            else:
                out.append(
                    {
                        "id": str(call.get("id") or "call"),
                        "type": "function",
                        "function": {
                            "name": str(call.get("name") or "tool"),
                            "arguments": call.get("arguments") or {},
                        },
                    }
                )
    return out


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


def completer_as_tool_loop_complete(
    completer: Any,
    *,
    tools: ToolRegistry,
    model: str,
    max_tokens: int | None = None,
) -> Any:
    """Public adapter: Completer → ConversationalToolLoopRunner ``complete`` fn."""
    return _as_complete_fn(
        completer, tools=tools, model=model, max_tokens=max_tokens
    )


__all__ = [
    "ProjectCodingConfig",
    "completer_as_tool_loop_complete",
    "mcp_host_config_class",
]
