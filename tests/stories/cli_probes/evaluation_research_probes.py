"""Story probe shims — handlers live in ``mechaharness.evaluation_surface``."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from mechaharness.cli_verb import CliProbe
from mechaharness.evaluation_surface import (
    EVALUATION_RESEARCH_HANDLERS,
    EvaluationResearchParams,
)


def _eval_probe(name: str, fn: Any) -> type[CliProbe]:
    class _P(CliProbe):
        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            del runtime
            assert isinstance(params, EvaluationResearchParams)
            out = fn(params.model_dump())
            if inspect.isawaitable(out):
                out = await out
            return out

    _P.name = name
    _P.params_model = EvaluationResearchParams
    _P.__name__ = f"{name}_probe"
    _P.__qualname__ = _P.__name__
    return _P


def evaluation_research_cli_probe_classes() -> dict[str, type[CliProbe]]:
    return {
        name: _eval_probe(name, fn)
        for name, fn in EVALUATION_RESEARCH_HANDLERS.items()
    }


__all__ = [
    "EVALUATION_RESEARCH_HANDLERS",
    "EvaluationResearchParams",
    "evaluation_research_cli_probe_classes",
]
