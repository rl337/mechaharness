"""Inference backends (Strategy pattern)."""

from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.registry import (
    create_inference,
    list_inference_backends,
    register_inference,
)

__all__ = [
    "InferenceStrategy",
    "create_inference",
    "list_inference_backends",
    "register_inference",
]
