"""Story probe shims — handlers live in ``mechaharness.pure_api_surface``."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from mechaharness.cli_verb import CliProbe
from mechaharness.pure_api_surface import PURE_API_HANDLERS, PureApiParams


def _pure_api_probe(name: str, fn: Any) -> type[CliProbe]:
    class _P(CliProbe):
        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            del runtime
            assert isinstance(params, PureApiParams)
            out = fn(params.model_dump())
            if inspect.isawaitable(out):
                out = await out
            return out

    _P.name = name
    _P.params_model = PureApiParams
    _P.__name__ = f"{name}_probe"
    _P.__qualname__ = _P.__name__
    return _P


def pure_api_cli_probe_classes() -> dict[str, type[CliProbe]]:
    return {name: _pure_api_probe(name, fn) for name, fn in PURE_API_HANDLERS.items()}


__all__ = ["PURE_API_HANDLERS", "PureApiParams", "pure_api_cli_probe_classes"]
