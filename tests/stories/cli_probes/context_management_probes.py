"""Story probe shims — handlers live in ``mechaharness.context_surface``."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from mechaharness.cli_verb import CliProbe
from mechaharness.context_surface import (
    CONTEXT_MANAGEMENT_HANDLERS,
    ContextManagementParams,
)


def _context_probe(name: str, fn: Any) -> type[CliProbe]:
    class _P(CliProbe):
        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            del runtime
            assert isinstance(params, ContextManagementParams)
            out = fn(params.model_dump())
            if inspect.isawaitable(out):
                out = await out
            return out

    _P.name = name
    _P.params_model = ContextManagementParams
    _P.__name__ = f"{name}_probe"
    _P.__qualname__ = _P.__name__
    return _P


def context_management_cli_probe_classes() -> dict[str, type[CliProbe]]:
    return {
        name: _context_probe(name, fn)
        for name, fn in CONTEXT_MANAGEMENT_HANDLERS.items()
    }


__all__ = [
    "CONTEXT_MANAGEMENT_HANDLERS",
    "ContextManagementParams",
    "context_management_cli_probe_classes",
]
