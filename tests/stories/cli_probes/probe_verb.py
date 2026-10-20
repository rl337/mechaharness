"""Single ``probe`` verb dispatching to the test ``CliProbe`` map multibind."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel, ConfigDict

from mechaharness.cli_verb import CliProbe, CliVerb


class ProbeParams(BaseModel):
    """``probe: {name: …, …probe fields}``."""

    model_config = ConfigDict(extra="allow")

    name: str


class ProbeVerb(CliVerb):
    name = "probe"
    params_model = ProbeParams

    def __init__(self, probes: dict[str, CliProbe]) -> None:
        self._probes = probes

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        assert isinstance(params, ProbeParams)
        raw = params.model_dump()
        name = str(raw.pop("name"))
        probe = self._probes.get(name)
        if probe is None:
            known = ", ".join(sorted(self._probes))
            raise KeyError(f"unknown CLI probe {name!r}; known: {known}")
        probe_params = probe.params_model.model_validate(raw)
        out = probe.run(probe_params, runtime)
        if inspect.isawaitable(out):
            out = await out
        return out


__all__ = ["ProbeParams", "ProbeVerb"]
