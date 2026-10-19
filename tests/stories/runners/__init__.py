"""Story-kind runners, split by domain; ``run_story`` is the thin dispatcher.

Each domain module exposes ``RUNNERS`` (story ``kind`` → coroutine). Add a new
kind in the module that owns the concept, then it is picked up here.
"""

from __future__ import annotations

from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import StoryRunner
from tests.stories.runners.access_authority import RUNNERS as ACCESS_AUTHORITY_RUNNERS
from tests.stories.runners.context_management import RUNNERS as CONTEXT_MANAGEMENT_RUNNERS
from tests.stories.runners.decision_plane import RUNNERS as DECISION_PLANE_RUNNERS
from tests.stories.runners.evaluation_research import RUNNERS as EVALUATION_RESEARCH_RUNNERS
from tests.stories.runners.graph_execution import RUNNERS as GRAPH_EXECUTION_RUNNERS
from tests.stories.runners.graph_recipes import RUNNERS as GRAPH_RECIPES_RUNNERS
from tests.stories.runners.harness_runs import RUNNERS as HARNESS_RUNS_RUNNERS
from tests.stories.runners.inspiration_primitives import RUNNERS as INSPIRATION_PRIMITIVES_RUNNERS
from tests.stories.runners.lifecycle_extensions import RUNNERS as LIFECYCLE_EXTENSIONS_RUNNERS

STORY_RUNNERS: dict[str, StoryRunner] = {}
for _domain in (
    HARNESS_RUNS_RUNNERS,
    ACCESS_AUTHORITY_RUNNERS,
    GRAPH_EXECUTION_RUNNERS,
    GRAPH_RECIPES_RUNNERS,
    DECISION_PLANE_RUNNERS,
    CONTEXT_MANAGEMENT_RUNNERS,
    LIFECYCLE_EXTENSIONS_RUNNERS,
    EVALUATION_RESEARCH_RUNNERS,
    INSPIRATION_PRIMITIVES_RUNNERS,
):
    overlap = STORY_RUNNERS.keys() & _domain.keys()
    if overlap:
        raise RuntimeError(f"duplicate story kinds across runner modules: {sorted(overlap)}")
    STORY_RUNNERS.update(_domain)


async def run_story(case: StoryCase, backend: StoryBackend) -> None:
    meta = case.load_json("story.json")
    kind = meta["kind"]
    if backend.mode == "live" and case.adapter == "in_process":
        raise AssertionError(
            f"{case.label}: in_process stories must not be collected in live mode"
        )
    try:
        runner = STORY_RUNNERS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown story kind {kind!r} in {case.label}") from exc
    await runner(case, backend)


__all__ = ["STORY_RUNNERS", "StoryRunner", "run_story"]
