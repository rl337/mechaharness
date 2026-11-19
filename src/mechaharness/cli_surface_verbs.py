"""Product CLI verbs for library-surface diagnostics (context / eval / pure API).

Each former probe name is a stable verb hosts and ``user_story`` walks can call.
Handlers live in ``*_surface`` modules; this file only binds ``CliVerb`` wrappers.
"""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from mechaharness.cli_verb import CliVerb
from mechaharness.context_surface import (
    CONTEXT_MANAGEMENT_HANDLERS,
    CONTEXT_PARAMETER_MODELS,
    ContextManagementParams,
)
from mechaharness.core.types import CompletionRequest
from mechaharness.evaluation_surface import (
    EVALUATION_PARAMETER_MODELS,
    EVALUATION_RESEARCH_HANDLERS,
    EvaluationResearchParams,
)
from mechaharness.inference.openai_compat import domain_request_to_wire
from mechaharness.inference.openai_request import OpenAIRequestPolicy
from mechaharness.pure_api_surface import PURE_API_HANDLERS, PureApiParams


class InspectOpenAIRequestParams(BaseModel):
    endpoint: str
    request: CompletionRequest
    compare_to: CompletionRequest | None = None


class InspectOpenAIRequestVerb(CliVerb):
    """Inspect provider-normalized body identity without issuing HTTP."""

    name = "inspect_openai_request"
    params_model = InspectOpenAIRequestParams

    def __init__(self, request_policy: OpenAIRequestPolicy) -> None:
        self.request_policy = request_policy

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = InspectOpenAIRequestParams.model_validate(params.model_dump())

        def inspect_request(request: CompletionRequest) -> dict[str, Any]:
            wire = domain_request_to_wire(request, default_model=request.model)
            return self.request_policy.prepare(
                wire.model_dump(mode="json", exclude_none=True),
                request.extra,
                endpoint=body.endpoint,
            ).diagnostics()

        report = inspect_request(body.request)
        if body.compare_to is not None:
            report["body_changed"] = (
                report["request_body_digest"]
                != inspect_request(body.compare_to)["request_body_digest"]
            )
        return report


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
    verbs: dict[str, type[CliVerb]] = {InspectOpenAIRequestVerb.name: InspectOpenAIRequestVerb}
    for name, fn in CONTEXT_MANAGEMENT_HANDLERS.items():
        verbs[name] = _make_surface_verb(
            name, fn, CONTEXT_PARAMETER_MODELS.get(name, ContextManagementParams)
        )
    for name, fn in PURE_API_HANDLERS.items():
        verbs[name] = _make_surface_verb(name, fn, PureApiParams)
    for name, fn in EVALUATION_RESEARCH_HANDLERS.items():
        verbs[name] = _make_surface_verb(
            name, fn, EVALUATION_PARAMETER_MODELS.get(name, EvaluationResearchParams)
        )
    return verbs


__all__ = ["surface_cli_verb_classes"]
