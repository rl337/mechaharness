"""Tests for SettingsConfig inference/harness class maps."""

from __future__ import annotations

import pytest
from pyiv import get_injector

from mechaharness.config import Settings
from mechaharness.di import SettingsConfig, list_inference_backends
from mechaharness.inference.base import InferenceStrategy


def test_builtin_backends_mapped() -> None:
    backends = list_inference_backends()
    for name in ("openai", "openai_compat", "anthropic", "lmstudio", "vllm", "ollama"):
        assert name in backends


@pytest.mark.asyncio
async def test_lmstudio_defaults() -> None:
    config = SettingsConfig(Settings(inference_backend="lmstudio"))
    strategy = get_injector(config).inject(InferenceStrategy)
    try:
        meta = strategy.describe()
        assert meta["name"] == "openai_compat"
        assert "1234" in meta["base_url"]
    finally:
        await strategy.aclose()


def test_unknown_backend() -> None:
    with pytest.raises(KeyError, match="Unknown inference backend"):
        SettingsConfig(Settings(inference_backend="not-a-real-backend"))
