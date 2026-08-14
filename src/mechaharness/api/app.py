"""HTTP API surface (stable contract for non-Python clients)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from mechaharness import __version__
from mechaharness.config import get_settings
from mechaharness.factory import build_harness, build_inference
from mechaharness.harness.registry import list_harness_families
from mechaharness.inference.registry import list_inference_backends
from mechaharness.tools.base import ToolRegistry

app = FastAPI(
    title="MechaHarness",
    version=__version__,
    description="Agentic harness API — pluggable inference backends and harness families.",
)


class RunRequest(BaseModel):
    prompt: str
    backend: str | None = None
    family: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    system_prompt: str | None = None
    max_turns: int = 8
    temperature: float | None = None


class RunResponse(BaseModel):
    final_text: str | None
    turns: int
    messages: list[dict[str, Any]]
    events: list[dict[str, Any]] = Field(default_factory=list)


def _demo_tools() -> ToolRegistry:
    tools = ToolRegistry()

    @tools.tool(
        description="Echo text back.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    def echo(text: str) -> str:
        return text

    return tools


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/backends")
async def backends() -> dict[str, list[str]]:
    return {"backends": list_inference_backends()}


@app.get("/families")
async def families() -> dict[str, list[str]]:
    return {"families": list_harness_families()}


@app.post("/v1/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    settings = get_settings()
    backend = req.backend or settings.inference_backend
    family = req.family or settings.harness_family
    model = req.model or settings.model

    kwargs: dict[str, Any] = {}
    key = req.api_key if req.api_key is not None else settings.api_key
    url = req.base_url if req.base_url is not None else settings.base_url
    if key is not None:
        kwargs["api_key"] = key
    if url is not None:
        kwargs["base_url"] = url

    try:
        inference = build_inference(backend, model=model, **kwargs)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        try:
            harness = build_harness(
                family,
                inference=inference,
                model=model,
                tools=_demo_tools(),
                system_prompt=req.system_prompt or settings.system_prompt,
                max_turns=req.max_turns,
                temperature=req.temperature,
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        result = await harness.run(req.prompt)
        return RunResponse(
            final_text=result.final_text,
            turns=result.turns,
            messages=[m.model_dump() for m in result.messages],
            events=[e.model_dump() for e in result.events],
        )
    finally:
        await inference.aclose()
