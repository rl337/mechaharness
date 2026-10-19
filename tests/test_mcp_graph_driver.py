"""Stdio MCP adapter maps tools onto DurableGraphGenerator."""

from __future__ import annotations

import io
import json

from mechaharness.durable_graph_generator import FileGeneratorRunStore
from mechaharness.mcp_graph_driver import GeneratorMcpServer, build_generator


def test_mcp_stdio_ndjson_initialize_lists_tools(tmp_path) -> None:
    """Cursor's MCP client uses newline-delimited JSON, not Content-Length."""
    gen = build_generator(store_path=tmp_path / "runs.json")
    stdin = io.BytesIO()
    stdout = io.BytesIO()

    def send(obj: dict) -> None:
        stdin.write(json.dumps(obj).encode("utf-8") + b"\n")

    send(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "cursor-vscode", "version": "1.0.0"},
            },
        }
    )
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    stdin.seek(0)

    server = GeneratorMcpServer(gen, stdin=stdin, stdout=stdout)
    # Drain until stdin EOF (BytesIO returns b"").
    server.serve_forever()

    lines = [ln for ln in stdout.getvalue().split(b"\n") if ln.strip()]
    assert len(lines) >= 2
    init = json.loads(lines[0])
    assert init["id"] == 0
    assert init["result"]["protocolVersion"] == "2025-11-25"
    tools = json.loads(lines[1])
    assert tools["id"] == 1
    names = {t["name"] for t in tools["result"]["tools"]}
    assert "generator_start" in names
    assert "generator_resume" in names


def test_mcp_stdio_content_length_still_works(tmp_path) -> None:
    gen = build_generator(store_path=tmp_path / "runs.json")
    stdin = io.BytesIO()
    stdout = io.BytesIO()
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
    ).encode("utf-8")
    stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stdin.seek(0)

    server = GeneratorMcpServer(gen, stdin=stdin, stdout=stdout)
    server.serve_forever()

    raw = stdout.getvalue()
    assert raw.startswith(b"Content-Length:")
    _, payload = raw.split(b"\r\n\r\n", 1)
    init = json.loads(payload)
    assert init["result"]["protocolVersion"] == "2024-11-05"


def test_mcp_tools_drive_demo_guidance(tmp_path) -> None:
    store = tmp_path / "runs.json"
    gen = build_generator(store_path=store)
    assert isinstance(gen._runs, FileGeneratorRunStore)  # noqa: SLF001
    server = GeneratorMcpServer(gen)

    recipes = server.call_tool("generator_list_recipes", {})
    assert any(r["recipe_id"] == "demo_guidance" for r in recipes["recipes"])

    y1 = server.call_tool(
        "generator_start",
        {
            "recipe_id": "demo_guidance",
            "run_id": "mcp-unit-1",
            "controller_id": "unit",
            "inputs": {"scene_brief": "exhausted sword work"},
        },
    )
    assert y1["kind"] == "advice_requested"
    assert y1["request_id"]

    # Simulate process restart: new server, same file store.
    gen2 = build_generator(store_path=store)
    server2 = GeneratorMcpServer(gen2)
    insp = server2.call_tool("generator_inspect", {"run_id": "mcp-unit-1"})
    assert insp["phase"] == "guidance_required"
    assert insp["pending_request"]["request_id"] == y1["request_id"]

    y2 = server2.call_tool(
        "generator_resume",
        {
            "run_id": "mcp-unit-1",
            "expected_sequence": y1["sequence"],
            "request_id": y1["request_id"],
            "choice_id": "precise",
            "controller_id": "unit",
            "idempotency_key": "k1",
        },
    )
    assert y2["kind"] == "completed"
