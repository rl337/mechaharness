"""Shared factory helpers for wiring inference + harness from settings/CLI flags."""

from __future__ import annotations

from typing import Any

from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.registry import create_harness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.registry import create_inference
from mechaharness.tools.base import ToolRegistry


def build_inference(
    backend: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> InferenceStrategy:
    opts: dict[str, Any] = dict(kwargs)
    if api_key is not None:
        opts["api_key"] = api_key
    if base_url is not None:
        opts["base_url"] = base_url
    if model is not None:
        opts["default_model"] = model
    return create_inference(backend, **opts)


def build_harness(
    family: str,
    *,
    inference: InferenceStrategy,
    model: str,
    tools: ToolRegistry | None = None,
    system_prompt: str | None = None,
    max_turns: int = 8,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AbstractHarness:
    config = HarnessConfig(
        model=model,
        system_prompt=system_prompt,
        max_turns=max_turns,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return create_harness(family, inference=inference, tools=tools, config=config)
