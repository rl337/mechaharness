"""Single ``probe`` verb dispatching to the test ``CliProbe`` map multibind."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel, ConfigDict

from mechaharness.cli_verb import CliProbe, CliVerb


class ProbeParams(BaseModel):
    """``probe: {name: <catalog key>, …probe fields}``.

    Catalog key is always ``name``. Payload fields that also need a ``name``
    (e.g. ``OperationContract``) go under ``params:``.
    """

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
        probe_id = str(raw.pop("name"))
        nested = raw.pop("params", None)
        if isinstance(nested, dict):
            raw = {**raw, **nested}
        probe = self._probes.get(probe_id)
        if probe is None:
            known = ", ".join(sorted(self._probes))
            raise KeyError(f"unknown CLI probe {probe_id!r}; known: {known}")
        probe_params = probe.params_model.model_validate(raw)
        out = probe.run(probe_params, runtime)
        if inspect.isawaitable(out):
            out = await out
        return out


__all__ = ["ProbeParams", "ProbeVerb"]
