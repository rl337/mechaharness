"""Tests for inference registry and OpenAI-compat parsing helpers."""

from __future__ import annotations

import pytest

from mechaharness.inference.registry import create_inference, list_inference_backends


def test_builtin_backends_registered() -> None:
    backends = list_inference_backends()
    for name in ("openai", "openai_compat", "anthropic", "lmstudio", "vllm", "ollama"):
        assert name in backends


def test_create_lmstudio_defaults() -> None:
    strategy = create_inference("lmstudio")
    meta = strategy.describe()
    assert meta["name"] == "openai_compat"
    assert "1234" in meta["base_url"]


def test_unknown_backend() -> None:
    with pytest.raises(KeyError, match="Unknown inference backend"):
        create_inference("not-a-real-backend")
