"""Non-DI helpers: OpenAPI ``run()`` and listing, backed by recipe graphs."""

from __future__ import annotations

from typing import Any

from mechaharness.config import Settings
from mechaharness.core.contract import RunRequest, RunResponse
from mechaharness.di import build_injector
from mechaharness.inference.base import InferenceStrategy
from mechaharness.tools.base import ToolRegistry


def settings_from_request(request: RunRequest) -> Settings:
    base = Settings()
    return Settings(
        inference_backend=request.backend or base.inference_backend,
        harness_family=request.family or base.harness_family,
        model=request.model or base.model,
        api_key=request.api_key if request.api_key is not None else base.api_key,
        base_url=request.base_url if request.base_url is not None else base.base_url,
        system_prompt=(
            request.system_prompt if request.system_prompt is not None else base.system_prompt
        ),
        max_turns=request.max_turns,
        temperature=request.temperature if request.temperature is not None else base.temperature,
        max_tokens=base.max_tokens,
        host=base.host,
        port=base.port,
    )


async def run(request: RunRequest, *, tools: ToolRegistry | None = None) -> RunResponse:
    """Run a prompt via Agentic Recipe ``harness_run`` (OpenAPI / CLI facade)."""
    from mechaharness.recipe_runner import run_harness_recipe

    return await run_harness_recipe(request, tools=tools)


async def describe(settings: Settings) -> dict[str, Any]:
    """Describe a backend Strategy (used by recipe runner and legacy callers)."""
    injector = build_injector(settings)
    strategy: InferenceStrategy = injector.inject(InferenceStrategy)
    try:
        return strategy.describe()
    finally:
        await strategy.aclose()


__all__ = [
    "describe",
    "run",
    "settings_from_request",
]
