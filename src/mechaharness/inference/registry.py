"""Registry / factory for inference strategies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mechaharness.inference.base import InferenceStrategy

StrategyFactory = Callable[..., InferenceStrategy]

_REGISTRY: dict[str, StrategyFactory] = {}


def register_inference(name: str) -> Callable[[StrategyFactory], StrategyFactory]:
    """Decorator to register a strategy factory under a short backend name."""

    def decorator(factory: StrategyFactory) -> StrategyFactory:
        key = name.lower()
        if key in _REGISTRY:
            raise ValueError(f"Inference backend already registered: {name}")
        _REGISTRY[key] = factory
        return factory

    return decorator


def list_inference_backends() -> list[str]:
    return sorted(_REGISTRY)


def create_inference(backend: str, **kwargs: Any) -> InferenceStrategy:
    """Instantiate a registered inference strategy by name."""
    key = backend.lower()
    try:
        factory = _REGISTRY[key]
    except KeyError as exc:
        known = ", ".join(list_inference_backends()) or "(none)"
        raise KeyError(f"Unknown inference backend {backend!r}. Known: {known}") from exc
    return factory(**kwargs)


def _ensure_builtins_loaded() -> None:
    # Import side-effects register built-in strategies.
    from mechaharness.inference import anthropic as _anthropic  # noqa: F401
    from mechaharness.inference import openai_compat as _openai_compat  # noqa: F401


_ensure_builtins_loaded()
