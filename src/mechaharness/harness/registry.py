"""Registry / factory for harness families."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.families import AnthropicToolsHarness, OpenAIToolsHarness
from mechaharness.harness.react import ReactHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.tools.base import ToolRegistry

HarnessFactory = Callable[..., AbstractHarness]

_REGISTRY: dict[str, type[AbstractHarness]] = {
    "tool_loop": ToolLoopHarness,
    "react": ReactHarness,
    "openai_tools": OpenAIToolsHarness,
    "anthropic_tools": AnthropicToolsHarness,
}


def register_harness(name: str, cls: type[AbstractHarness]) -> None:
    key = name.lower()
    if key in _REGISTRY:
        raise ValueError(f"Harness family already registered: {name}")
    _REGISTRY[key] = cls


def list_harness_families() -> list[str]:
    return sorted(_REGISTRY)


def create_harness(
    family: str,
    *,
    inference: InferenceStrategy,
    tools: ToolRegistry | None = None,
    config: HarnessConfig,
    **kwargs: Any,
) -> AbstractHarness:
    key = family.lower()
    try:
        cls = _REGISTRY[key]
    except KeyError as exc:
        known = ", ".join(list_harness_families())
        raise KeyError(f"Unknown harness family {family!r}. Known: {known}") from exc
    return cls(inference=inference, tools=tools, config=config, **kwargs)
