"""Inference backends (Strategy pattern)."""

from mechaharness.inference.anthropic import AnthropicStrategy
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.openai_compat import OpenAICompatStrategy

__all__ = [
    "AnthropicStrategy",
    "InferenceStrategy",
    "OpenAICompatStrategy",
]
