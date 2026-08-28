"""HTTP API surface (stable contract for non-Python clients)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from mechaharness import __version__
from mechaharness.core.contract import RunRequest, RunResponse
from mechaharness.core.exceptions import MechaHarnessError
from mechaharness.di import list_harness_families, list_inference_backends
from mechaharness.factory import run as run_harness

app = FastAPI(
    title="MechaHarness",
    version=__version__,
    description="Agentic harness API — pluggable inference backends and harness families.",
)


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
    try:
        return await run_harness(req)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MechaHarnessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
