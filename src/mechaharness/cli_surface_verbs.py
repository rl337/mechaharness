"""Product CLI verbs for library-surface diagnostics (context / eval / pure API).

Each former probe name is a stable verb hosts and ``user_story`` walks can call.
Handlers live in ``*_surface`` modules; this file only binds ``CliVerb`` wrappers.
"""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from mechaharness.cli_verb import CliVerb
from mechaharness.context_surface import CONTEXT_MANAGEMENT_HANDLERS, ContextManagementParams
from mechaharness.evaluation_surface import (
    EVALUATION_RESEARCH_HANDLERS,
    EvaluationResearchParams,
)
from mechaharness.pure_api_surface import PURE_API_HANDLERS, PureApiParams


def _make_surface_verb(
    name: str,
    fn: Any,
    params_model: type[BaseModel],
) -> type[CliVerb]:
    class _V(CliVerb):
        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            del runtime
            raw = params.model_dump()
            out = fn(raw)
            if inspect.isawaitable(out):
                out = await out
            assert isinstance(out, dict)
            return out

    _V.name = name
    _V.params_model = params_model
    _V.__name__ = f"{name}_verb"
    _V.__qualname__ = _V.__name__
    return _V


def surface_cli_verb_classes() -> dict[str, type[CliVerb]]:
    verbs: dict[str, type[CliVerb]] = {}
    for name, fn in CONTEXT_MANAGEMENT_HANDLERS.items():
        verbs[name] = _make_surface_verb(name, fn, ContextManagementParams)
    for name, fn in PURE_API_HANDLERS.items():
        verbs[name] = _make_surface_verb(name, fn, PureApiParams)
    for name, fn in EVALUATION_RESEARCH_HANDLERS.items():
        verbs[name] = _make_surface_verb(name, fn, EvaluationResearchParams)
    return verbs


__all__ = ["surface_cli_verb_classes"]
