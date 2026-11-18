"""Luna Chat Completions: inject reasoning_effort=none when tools are present."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pyiv.http import MemoryAsyncHttpClient

from mechaharness.config import Settings
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    Role,
    ToolDefinition,
)
from mechaharness.inference.openai_compat import OpenAICompatStrategy


def _strategy(*, model: str = "gpt-6-luna") -> OpenAICompatStrategy:
    settings = Settings.model_construct(
        inference_backend="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model=model,
        harness_family="tool_loop",
        system_prompt=None,
        max_turns=8,
        temperature=None,
        max_tokens=None,
        host="127.0.0.1",
        port=8080,
    )
    return OpenAICompatStrategy(settings, client=MemoryAsyncHttpClient(), timeout=5.0)


@dataclass(frozen=True)
class LunaBodyCase:
    label: str
    model: str
    with_tools: bool
    extra: dict | None
    expect_effort: str | None
    max_tokens: int | None = None
    expect_max_completion_tokens: int | None = None
    expect_max_tokens: int | None = None


@pytest.mark.parametrize(
    "case",
    [
        LunaBodyCase(
            label="luna_tools_injects_none",
            model="gpt-6-luna",
            with_tools=True,
            extra=None,
            expect_effort="none",
        ),
        LunaBodyCase(
            label="luna_no_tools_no_effort",
            model="gpt-6-luna",
            with_tools=False,
            extra=None,
            expect_effort=None,
        ),
        LunaBodyCase(
            label="non_luna_tools_no_effort",
            model="gpt-4o-mini",
            with_tools=True,
            extra=None,
            expect_effort=None,
        ),
        LunaBodyCase(
            label="luna_tools_respects_explicit_extra",
            model="gpt-6-luna",
            with_tools=True,
            extra={"reasoning_effort": "low"},
            expect_effort="low",
        ),
        LunaBodyCase(
            label="luna_remaps_max_tokens",
            model="gpt-6-luna",
            with_tools=False,
            extra=None,
            expect_effort=None,
            max_tokens=256,
            expect_max_completion_tokens=256,
        ),
        LunaBodyCase(
            label="luna_strips_mh_node_id_extra",
            model="gpt-6-luna",
            with_tools=False,
            extra={"node_id": "infer", "snapshot_id": "snap-1"},
            expect_effort=None,
        ),
    ],
    ids=lambda c: c.label,
)
def test_luna_reasoning_effort_in_build_body(case: LunaBodyCase) -> None:
    strategy = _strategy(model=case.model)
    tools = (
        [
            ToolDefinition(
                name="ping",
                description="Ping",
                parameters={"type": "object", "properties": {}},
            )
        ]
        if case.with_tools
        else None
    )
    kwargs: dict = {
        "model": case.model,
        "messages": [ChatMessage(role=Role.USER, content="hi")],
        "tools": tools,
    }
    if case.extra is not None:
        kwargs["extra"] = case.extra
    if case.max_tokens is not None:
        kwargs["max_tokens"] = case.max_tokens
    request = CompletionRequest(**kwargs)
    body = strategy._build_body(request)
    if case.expect_effort is None:
        assert "reasoning_effort" not in body
    else:
        assert body["reasoning_effort"] == case.expect_effort
    if case.expect_max_completion_tokens is not None:
        assert body.get("max_completion_tokens") == case.expect_max_completion_tokens
        assert "max_tokens" not in body
    if case.expect_max_tokens is not None:
        assert body.get("max_tokens") == case.expect_max_tokens
    assert "node_id" not in body
    assert "snapshot_id" not in body
