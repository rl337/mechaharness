"""Single ``probe`` verb dispatching to the test ``CliProbe`` map multibind.

Stories may inline ``probe: {name, …}`` or load a human-readable plan file::

    probe:
      path: plans/eval_matrix.yaml

Plan files use the same field shape (``name`` + probe params) plus optional
``summary`` for readers.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from mechaharness.cli_verb import CliProbe, CliVerb


class ProbeParams(BaseModel):
    """``probe: {name: …}`` or ``probe: {path: plans/….yaml}``."""

    model_config = ConfigDict(extra="allow")

    name: str | None = None
    path: str | None = None
    summary: str | None = None

    @model_validator(mode="after")
    def _name_or_path(self) -> ProbeParams:
        if self.path or self.name:
            return self
        raise ValueError("probe requires name= or path=")


def _load_probe_plan(path: str | Path, *, base_dir: Path | None) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_absolute():
        root = base_dir if base_dir is not None else Path.cwd()
        file_path = (root / file_path).resolve()
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{file_path}: probe plan root must be a mapping")
    if not data.get("name"):
        raise ValueError(f"{file_path}: probe plan missing name=")
    return data


class ProbeVerb(CliVerb):
    name = "probe"
    params_model = ProbeParams

    def __init__(self, probes: dict[str, CliProbe]) -> None:
        self._probes = probes

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        assert isinstance(params, ProbeParams)
        raw = params.model_dump(exclude_none=True)
        path = raw.pop("path", None)
        if path:
            loaded = _load_probe_plan(
                path, base_dir=getattr(runtime, "bind_base_dir", None)
            )
            # File is the document; command-level keys (if any) override.
            raw = {**loaded, **raw}
        # String ``summary`` is documentation-only; dict/list summaries are
        # probe payload (e.g. harness fingerprint provenance).
        doc_summary = raw.get("summary")
        if isinstance(doc_summary, str):
            raw.pop("summary", None)
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
