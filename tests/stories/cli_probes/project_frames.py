"""Fangore interrupts and reopens a recursive project graph."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mechaharness.cli_verb import CliProbe
from tests.support.graph_call_frames import walk_project_frames


class FrameParams(BaseModel):
    depth: int = Field(ge=1, le=100)


class ProjectFrameProbe(CliProbe):
    name = "resume_project_frames"
    params_model = FrameParams

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        assert isinstance(params, FrameParams)
        return await walk_project_frames(Path(runtime.workspace_root), params.depth, crash=True)
