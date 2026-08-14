"""Non-DI helpers: OpenAPI ``run()`` and listing, backed by a pyiv injector."""

from __future__ import annotations

from typing import Any

from mechaharness.config import Settings
from mechaharness.core.contract import RunRequest, RunResponse
from mechaharness.di import build_injector
from mechaharness.harness.base import AbstractHarness
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
    """Run a prompt using the OpenAPI contract (hides the injector)."""
    settings = settings_from_request(request)
    injector = build_injector(settings, tools=tools)
    inference: InferenceStrategy = injector.inject(InferenceStrategy)
    try:
        harness: AbstractHarness = injector.inject(AbstractHarness)
        result = await harness.run(request.prompt)
        return RunResponse(
            final_text=result.final_text,
            turns=result.turns,
            messages=[m.model_dump() for m in result.messages],
            events=[e.model_dump() for e in result.events],
        )
    finally:
        await inference.aclose()


async def describe(settings: Settings) -> dict[str, Any]:
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
