"""Inference backends (Strategy pattern)."""

from mechaharness.inference.anthropic import AnthropicStrategy
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from mechaharness.inference.openai_wire import (
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
)

__all__ = [
    "AnthropicStrategy",
    "InferenceStrategy",
    "MockInferenceStrategy",
    "OpenAIChatCompletionRequest",
    "OpenAIChatCompletionResponse",
    "OpenAICompatStrategy",
]
