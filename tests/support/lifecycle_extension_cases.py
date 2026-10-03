"""Interpreter for lifecycle_extension fixture cases."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import Ability, AccessPolicy, ExtensionRewrite, FsWrite
from mechaharness.core.events import InMemoryEventLog
from mechaharness.core.types import ChatMessage, Role, ToolCall
from mechaharness.harness.base import HarnessConfig
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.lifecycle_extension import (
    BeforeTool,
    Block,
    ExtensionEffect,
    LifecycleExtension,
    LifecycleExtensionContext,
    LifecycleExtensionRegistry,
    ObserveBefore,
    Rewrite,
)
from mechaharness.tools.base import ToolRegistry
from tests.fakes import ScriptedInference
from tests.support.di import make_harness

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "lifecycle_extension"


class _WatchA(LifecycleExtension):
    extension_id = "acme:watch_a"
    boundary = BeforeTool
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key())


class _WatchB(LifecycleExtension):
    extension_id = "acme:watch_b"
    boundary = BeforeTool
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key())


class _SandboxRewrite(LifecycleExtension):
    extension_id = "acme:sandbox_rewrite"
    boundary = BeforeTool
    modes = frozenset({Rewrite})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        path = str(context.arguments.get("path", ""))
        return ExtensionEffect(
            mode=Rewrite.key(),
            rewrite_arguments={"path": f"/sandbox/{path}"},
        )


class _BlockWrite(LifecycleExtension):
    extension_id = "acme:block_write"
    boundary = BeforeTool
    modes = frozenset({Block})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(
            mode=Block.key(),
            block=True,
            block_message="blocked by host extension",
        )


class _RewriteNeedsGrant(LifecycleExtension):
    extension_id = "acme:rewrite_needs_grant"
    boundary = BeforeTool
    modes = frozenset({Rewrite})
    required_grants = (ExtensionRewrite,)

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        path = str(context.arguments.get("path", ""))
        return ExtensionEffect(
            mode=Rewrite.key(),
            rewrite_arguments={"path": f"/sandbox/{path}"},
        )


def iter_cases() -> Iterator[dict[str, Any]]:
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        data.setdefault("id", path.stem)
        yield data


def _tools() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(
        description="Write a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        grants=[FsWrite],
        ability=Ability.BASIC,
    )
    def write_file(path: str) -> str:
        return f"wrote {path}"

    return registry


async def run_case(case: dict[str, Any]) -> dict[str, Any]:
    mode = case["mode"]
    if mode == "observe":
        extensions: list[LifecycleExtension] = [_WatchA(), _WatchB()]
        envelope_grants: list[object] = [FsWrite]
    elif mode == "rewrite":
        extensions = [_SandboxRewrite()]
        envelope_grants = [FsWrite]
    elif mode == "block":
        extensions = [_BlockWrite()]
        envelope_grants = [FsWrite]
    elif mode == "authority_deny":
        extensions = [_RewriteNeedsGrant()]
        envelope_grants = [FsWrite]  # missing ExtensionRewrite
    else:
        raise ValueError(f"unknown lifecycle_extension case mode {mode!r}")

    log = InMemoryEventLog()
    inference = ScriptedInference(
        [
            ChatMessage(
                role=Role.ASSISTANT,
                content=None,
                tool_calls=[
                    ToolCall(id="1", name="write_file", arguments={"path": "a.txt"})
                ],
            ),
            ChatMessage(role=Role.ASSISTANT, content="done"),
        ]
    )
    result = await make_harness(
        inference,
        tools=_tools(),
        config=HarnessConfig(model="test", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=log,
        access_policy=AccessPolicy(grants=[FsWrite]),
        lifecycle_extensions=LifecycleExtensionRegistry(extensions),
        capability_envelope=CapabilityEnvelope.from_grants(envelope_grants),
    ).run("write")
    rid = result.events[0].run_id if result.events else None
    ext_events = [
        e for e in log.query(run_id=rid) if e.type == "core:extension_applied"
    ]
    before = [e for e in ext_events if e.payload.get("boundary") == "core:before_tool"]
    tool_msgs = [m.content or "" for m in result.messages if m.role == Role.TOOL]
    tool_result = tool_msgs[0] if tool_msgs else ""
    focus = before or ext_events
    return {
        "extension_ids": [e.payload.get("extension_id") for e in focus],
        "default_ran": all(bool(e.payload.get("default_ran")) for e in focus)
        if focus
        else False,
        "applied_rewrite": any(bool(e.payload.get("applied_rewrite")) for e in focus),
        "applied_block": any(bool(e.payload.get("applied_block")) for e in focus),
        "tool_result_contains": tool_result,
        "mode": focus[0].payload.get("mode") if focus else None,
    }


def assert_expect(actual: dict[str, Any], expect: dict[str, Any]) -> None:
    for key, wanted in expect.items():
        got = actual[key]
        if key.endswith("_contains") and isinstance(wanted, str):
            assert wanted in str(got), f"{key}: {wanted!r} not in {got!r}"
        else:
            assert got == wanted, f"{key}: {got!r} != {wanted!r}"
