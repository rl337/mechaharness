"""Stdio MCP adapter for :class:`DurableGraphGenerator` (DG-05 / R-IOC-MCP).

Exposes transport-neutral generator ops as MCP tools so a frontier client
(Cursor, Codex, …) can drive a durable run from its existing session:

1. ``generator_start`` → may return ``advice_requested`` as the tool result
2. Client reasons in-session
3. ``generator_resume`` with guidance → next yield / completion

Protocol: JSON-RPC 2.0 over stdio. Cursor's bundled MCP client uses
**newline-delimited JSON** (one object per line). We also accept LSP-style
``Content-Length`` framing for other hosts. Implemented without the official
``mcp`` package so Python 3.9 hosts work.

Diagnostics go to **stderr** only — stdout is protocol.

Environment:

- ``MECHA_GENERATOR_STORE`` — JSON run-store path (default
  ``.mechaharness/generator-runs.json`` under cwd)
- ``MECHA_GENERATOR_CONTROLLER`` — default controller id (default
  ``mcp-driver``)
- ``MECHA_MCP_HOST`` — ``project_coding`` binds
  :class:`~mechaharness.project_coding.ProjectCodingConfig` (workspace tools +
  Settings / ``MECHA_BASE_URL``). Unset → bare registry generator.
- ``MECHA_WORKSPACE`` — project root for coding tools (default: cwd)
- ``MECHA_BASE_URL`` / ``MECHA_MODEL`` / ``MECHA_API_KEY`` /
  ``MECHA_INFERENCE_BACKEND`` — local inference (blessed on MCP ``env``)

Run::

    python -m mechaharness.mcp_graph_driver

End-to-end driver loop (doctest / pytest ``--doctest-modules``). This is the
blessed offline example of frontier IoC: start → advice → process restart →
inspect → resume → completed. A real MCP client talks JSON-RPC over stdio;
``call_tool`` is the same mapping the transport invokes after ``tools/call``.

    >>> import io, tempfile
    >>> from pathlib import Path
    >>> from mechaharness.mcp_graph_driver import GeneratorMcpServer, build_generator
    >>> store = Path(tempfile.mkdtemp()) / "runs.json"
    >>> server = GeneratorMcpServer(
    ...     build_generator(store_path=store),
    ...     stdin=io.BytesIO(),
    ...     stdout=io.BytesIO(),
    ... )
    >>> recipes = server.call_tool("generator_list_recipes", {})
    >>> any(r["recipe_id"] == "demo_guidance" for r in recipes["recipes"])
    True
    >>> y1 = server.call_tool(
    ...     "generator_start",
    ...     {
    ...         "recipe_id": "demo_guidance",
    ...         "run_id": "doc-demo-1",
    ...         "controller_id": "docs",
    ...         "inputs": {"scene_brief": "exhausted sword work"},
    ...     },
    ... )
    >>> y1["kind"], y1["sequence"]
    ('advice_requested', 1)
    >>> bool(y1["request_id"])
    True
    >>> # Simulate MCP process exit: new server, same FileGeneratorRunStore.
    >>> server2 = GeneratorMcpServer(
    ...     build_generator(store_path=store),
    ...     stdin=io.BytesIO(),
    ...     stdout=io.BytesIO(),
    ... )
    >>> insp = server2.call_tool("generator_inspect", {"run_id": "doc-demo-1"})
    >>> insp["phase"]
    'guidance_required'
    >>> insp["pending_request"]["request_id"] == y1["request_id"]
    True
    >>> choice = (y1.get("payload") or {}).get("recommendation") or "precise"
    >>> y2 = server2.call_tool(
    ...     "generator_resume",
    ...     {
    ...         "run_id": "doc-demo-1",
    ...         "expected_sequence": y1["sequence"],
    ...         "request_id": y1["request_id"],
    ...         "choice_id": choice,
    ...         "controller_id": "docs",
    ...         "idempotency_key": "doc-demo-1:1",
    ...     },
    ... )
    >>> y2["kind"], y2["payload"]["result"]
    ('completed', 'ok')

Cursor-compatible NDJSON handshake (initialize + tools/list)::

    >>> import io, json
    >>> from mechaharness.mcp_graph_driver import GeneratorMcpServer, build_generator
    >>> stdin, stdout = io.BytesIO(), io.BytesIO()
    >>> def send(obj):
    ...     stdin.write(json.dumps(obj).encode("utf-8") + b"\\n")
    >>> send({
    ...     "jsonrpc": "2.0", "id": 0, "method": "initialize",
    ...     "params": {
    ...         "protocolVersion": "2025-11-25",
    ...         "capabilities": {},
    ...         "clientInfo": {"name": "example", "version": "0"},
    ...     },
    ... })
    >>> send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    >>> send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    >>> _ = stdin.seek(0)
    >>> store = Path(tempfile.mkdtemp()) / "ndjson-runs.json"
    >>> GeneratorMcpServer(
    ...     build_generator(store_path=store), stdin=stdin, stdout=stdout
    ... ).serve_forever()
    >>> lines = [ln for ln in stdout.getvalue().split(b"\\n") if ln.strip()]
    >>> init = json.loads(lines[0])
    >>> init["result"]["protocolVersion"]
    '2025-11-25'
    >>> names = {t["name"] for t in json.loads(lines[1])["result"]["tools"]}
    >>> "generator_start" in names and "generator_resume" in names
    True

See also: ``docs/reference/durable-graph-generators.md`` and durable
``kind: cli`` stories with a ``durable:`` session block.
"""

from __future__ import annotations

import io
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, BinaryIO, Callable, Literal, cast

from pyiv.time import PythonDateTimeService

from mechaharness.core.events import InMemoryEventLog
from mechaharness.durable_graph_generator import (
    DurableGraphGenerator,
    FileGeneratorRunStore,
    GuidanceResponse,
)
from mechaharness.graph_templates import GraphTemplateRegistry
from mechaharness.graph_templates.catalog import default_graph_template_classes

# Prefer the newest version Cursor advertises when the client offers it.
_SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
    "2024-10-07",
)
PROTOCOL_VERSION = _SUPPORTED_PROTOCOL_VERSIONS[0]
SERVER_NAME = "mechaharness-generator"
SERVER_VERSION = "0.6.0"

Framing = Literal["ndjson", "content-length"]


def _log(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def build_generator(
    *,
    store_path: str | Path | None = None,
    controller_default: str | None = None,
) -> DurableGraphGenerator:
    """Construct a generator with a file-backed run store (MCP-process safe).

    When ``MECHA_MCP_HOST`` is ``project_coding`` (default), builds via
    :class:`~mechaharness.project_coding.ProjectCodingConfig` so Settings /
    MCP ``env`` bind ``openai_local`` and coding tools. Set
    ``MECHA_MCP_HOST=none`` for a bare registry-only generator (doctests).
    """
    del controller_default  # callers pass controller_id per op
    path = Path(
        store_path
        or os.environ.get("MECHA_GENERATOR_STORE")
        or Path.cwd() / ".mechaharness" / "generator-runs.json"
    )
    from mechaharness.project_coding import mcp_host_config_class

    host_cls = mcp_host_config_class()
    if host_cls is not None:
        from mechaharness.di import get_injector

        store = FileGeneratorRunStore(path)

        class _McpHostConfig(host_cls):  # type: ignore[misc,valid-type]
            def get_generator_run_store(self) -> FileGeneratorRunStore:
                return store

        return cast(
            DurableGraphGenerator,
            get_injector(_McpHostConfig).inject(DurableGraphGenerator),
        )

    templates = {name: cls() for name, cls in default_graph_template_classes().items()}
    registry = GraphTemplateRegistry(templates)
    return DurableGraphGenerator(
        registry=registry,
        run_store=FileGeneratorRunStore(path),
        event_log=InMemoryEventLog(),
        datetime_service=PythonDateTimeService(),
    )


def _default_controller() -> str:
    return os.environ.get("MECHA_GENERATOR_CONTROLLER") or "mcp-driver"


def _binary_stdio(stream: Any) -> BinaryIO:
    """Return a binary buffer for *stream* (doctest SpoofOut has no ``.buffer``)."""
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        return buf  # type: ignore[no-any-return]
    return io.BytesIO()


def _tool_defs() -> list[dict[str, Any]]:
    return [
        {
            "name": "generator_list_recipes",
            "description": (
                "List registered MechaHarness Agentic Recipes available to start "
                "as durable generator runs."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "generator_start",
            "description": (
                "Start a durable generator run for a registered recipe. Returns an "
                "ordered GraphYield. If kind is advice_requested, answer later with "
                "generator_resume (same driver session) — do not expect a recursive "
                "callback into this tool call."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["recipe_id"],
                "properties": {
                    "recipe_id": {
                        "type": "string",
                        "description": "Catalog id (e.g. verify_repair, demo_guidance)",
                    },
                    "inputs": {
                        "type": "object",
                        "description": (
                            "Recipe inputs. Optional guidance: array of GuidanceRequest "
                            "objects to force advice yields for demos."
                        ),
                    },
                    "run_id": {"type": "string"},
                    "controller_id": {
                        "type": "string",
                        "description": "Owning driver identity (defaults to env)",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "generator_resume",
            "description": (
                "Resume a durable run after a yield. For advice_requested, supply "
                "guidance matching request_id and expected_sequence from the prior yield."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["run_id", "expected_sequence"],
                "properties": {
                    "run_id": {"type": "string"},
                    "expected_sequence": {"type": "integer"},
                    "request_id": {"type": "string"},
                    "choice_id": {"type": "string"},
                    "text": {"type": "string"},
                    "structured": {"type": "object"},
                    "deferred": {"type": "boolean"},
                    "refused": {"type": "boolean"},
                    "idempotency_key": {"type": "string"},
                    "controller_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "generator_inspect",
            "description": "Inspect a run without advancing (pending question, cost, phase).",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {"run_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "generator_cancel",
            "description": "Cancel a durable generator run.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {
                    "run_id": {"type": "string"},
                    "expected_sequence": {"type": "integer"},
                    "controller_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    ]


class GeneratorMcpServer:
    """Minimal MCP server mapping tools → DurableGraphGenerator."""

    def __init__(
        self,
        generator: DurableGraphGenerator | None = None,
        *,
        stdin: BinaryIO | None = None,
        stdout: BinaryIO | None = None,
        framing: Framing | None = None,
    ) -> None:
        self._gen = generator or build_generator()
        self._stdin: BinaryIO = stdin if stdin is not None else _binary_stdio(sys.stdin)
        self._stdout: BinaryIO = (
            stdout if stdout is not None else _binary_stdio(sys.stdout)
        )
        # None → detect from the first inbound message (Cursor = ndjson).
        self._framing: Framing | None = framing
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "initialize": self._initialize,
            "ping": self._ping,
            "tools/list": self._tools_list,
            "tools/call": self._tools_call,
        }

    def serve_forever(self) -> None:
        _log(f"{SERVER_NAME} listening on stdio (store via MECHA_GENERATOR_STORE)")
        while True:
            msg = self._read_message()
            if msg is None:
                break
            if "method" in msg and "id" not in msg:
                # notification
                if msg.get("method") == "notifications/initialized":
                    _log("client initialized")
                continue
            self._dispatch(msg)

    def _read_message(self) -> dict[str, Any] | None:
        line = self._stdin.readline()
        if line == b"":
            return None
        stripped = line.lstrip()
        if self._framing is None:
            if stripped.startswith(b"{"):
                self._framing = "ndjson"
                _log("stdio framing: ndjson")
            elif line.lower().startswith(b"content-length:"):
                self._framing = "content-length"
                _log("stdio framing: content-length")
            else:
                # Skip BOM / blank / noise until a real frame appears.
                return self._read_message()

        if self._framing == "ndjson":
            text = line.decode("utf-8").strip()
            if not text:
                return self._read_message()
            parsed: object = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("MCP message must be a JSON object")
            return parsed

        # Content-Length: first line already consumed; finish headers + body.
        headers: dict[str, str] = {}
        if b":" in line:
            key, value = line.split(b":", 1)
            headers[key.decode("ascii").strip().lower()] = value.decode("ascii").strip()
        while True:
            hdr = self._stdin.readline()
            if hdr == b"":
                return None
            if hdr in (b"\r\n", b"\n"):
                break
            if b":" in hdr:
                key, value = hdr.split(b":", 1)
                headers[key.decode("ascii").strip().lower()] = (
                    value.decode("ascii").strip()
                )
        length_s = headers.get("content-length")
        if not length_s:
            _log("content-length framing missing Content-Length; ignoring")
            return self._read_message()
        raw = self._stdin.read(int(length_s))
        if not raw:
            return None
        parsed_cl: object = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed_cl, dict):
            raise ValueError("MCP message must be a JSON object")
        return parsed_cl

    def _write_message(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
        framing = self._framing or "ndjson"
        if framing == "ndjson":
            self._stdout.write(data + b"\n")
        else:
            header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
            self._stdout.write(header)
            self._stdout.write(data)
        self._stdout.flush()

    def _dispatch(self, msg: dict[str, Any]) -> None:
        req_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}
        if not isinstance(method, str):
            self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32600, "message": "invalid request"},
                }
            )
            return
        handler = self._handlers.get(method)
        if handler is None:
            self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )
            return
        try:
            safe_params = params if isinstance(params, dict) else {}
            if method == "tools/call":
                from mechaharness.mcp_progress import (
                    extract_progress_token,
                    mcp_progress_scope,
                )

                progress_token = extract_progress_token(safe_params)
                tool_name = safe_params.get("name")
                if progress_token is None:
                    _log(
                        "tools/call missing _meta.progressToken — "
                        "no notifications/progress (Cursor idle timeout may fire)"
                    )
                else:
                    _log(
                        f"tools/call progressToken={progress_token!r} "
                        f"tool={tool_name!r}"
                    )
                with mcp_progress_scope(
                    progress_token,
                    self._write_message,
                ) as progress:
                    if progress is not None:
                        progress.report(
                            str(tool_name) if isinstance(tool_name, str) else "tools/call"
                        )
                    result = handler(safe_params)
            else:
                result = handler(safe_params)
            self._write_message({"jsonrpc": "2.0", "id": req_id, "result": result})
        except Exception as exc:  # noqa: BLE001 — surface to MCP client
            _log(traceback.format_exc())
            self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": f"{type(exc).__name__}: {exc}"},
                }
            )

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        client_version = params.get("protocolVersion")
        negotiated = PROTOCOL_VERSION
        if isinstance(client_version, str) and client_version in _SUPPORTED_PROTOCOL_VERSIONS:
            negotiated = client_version
        elif isinstance(client_version, str):
            # Fall back to newest we support that the client might accept.
            negotiated = PROTOCOL_VERSION
        return {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "Drive MechaHarness graphs via generator_start / generator_resume. "
                "When a yield kind is advice_requested, answer in a later "
                "generator_resume call in this session."
            ),
        }

    def _ping(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        return {}

    def _tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        return {"tools": _tool_defs()}

    def _tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            raise ValueError("tools/call requires name")
        if not isinstance(arguments, dict):
            raise ValueError("tools/call arguments must be an object")
        result = self.call_tool(name, arguments)
        text = json.dumps(result, indent=2, sort_keys=True)
        return {"content": [{"type": "text", "text": text}], "structuredContent": result}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool by name (also used by offline trial clients)."""
        if name == "generator_list_recipes":
            return {
                "recipes": [r.model_dump(mode="json") for r in self._gen.list_recipes()]
            }
        if name == "generator_start":
            recipe_id = str(arguments["recipe_id"])
            inputs = dict(arguments.get("inputs") or {})
            # Demo convenience: MECHA_DEMO_GUIDANCE=1 injects a sample question.
            if not inputs.get("guidance") and os.environ.get("MECHA_DEMO_GUIDANCE") == "1":
                inputs["guidance"] = [
                    {
                        "question": (
                            "How should exhaustion affect the sword maneuver in this shot?"
                        ),
                        "choices": [
                            {
                                "id": "slow",
                                "label": "Slower, imperfect technique",
                            },
                            {
                                "id": "precise",
                                "label": "Precise maneuver followed by collapse",
                            },
                        ],
                        "recommendation": "precise",
                        "requested_authority": "artistic_direction",
                        "evidence_refs": ["artifact://demo/performance-analysis"],
                    }
                ]
            from mechaharness.mcp_progress import get_mcp_progress

            progress = get_mcp_progress()
            if progress is not None:
                progress.base_segments = [recipe_id]
                progress.report("start")
            y = self._gen.start(
                recipe_id,
                inputs,
                controller_id=str(arguments.get("controller_id") or _default_controller()),
                run_id=arguments.get("run_id"),
            )
            return y.model_dump(mode="json")
        if name == "generator_resume":
            run_id = str(arguments["run_id"])
            expected = int(arguments["expected_sequence"])
            response = None
            if any(
                k in arguments
                for k in ("choice_id", "text", "structured", "deferred", "refused", "request_id")
            ):
                response = GuidanceResponse(
                    request_id=str(arguments.get("request_id") or ""),
                    choice_id=arguments.get("choice_id"),
                    text=arguments.get("text"),
                    structured=dict(arguments.get("structured") or {}),
                    deferred=bool(arguments.get("deferred") or False),
                    refused=bool(arguments.get("refused") or False),
                )
            from mechaharness.mcp_progress import get_mcp_progress

            progress = get_mcp_progress()
            if progress is not None:
                try:
                    record = self._gen.inspect(run_id)
                    progress.base_segments = [str(record.recipe_id)]
                except Exception:  # noqa: BLE001
                    pass
                progress.report("resume")
            y = self._gen.resume(
                run_id,
                response,
                expected_sequence=expected,
                request_id=arguments.get("request_id"),
                idempotency_key=arguments.get("idempotency_key"),
                controller_id=str(
                    arguments.get("controller_id") or _default_controller()
                ),
            )
            return y.model_dump(mode="json")
        if name == "generator_inspect":
            insp = self._gen.inspect(str(arguments["run_id"]))
            return insp.model_dump(mode="json")
        if name == "generator_cancel":
            y = self._gen.cancel(
                str(arguments["run_id"]),
                controller_id=str(
                    arguments.get("controller_id") or _default_controller()
                ),
                expected_sequence=arguments.get("expected_sequence"),
            )
            return y.model_dump(mode="json")
        raise ValueError(f"unknown tool {name!r}")


def main(argv: list[str] | None = None) -> int:
    del argv
    GeneratorMcpServer().serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
