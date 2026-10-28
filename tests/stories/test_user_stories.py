"""Parametrized dual-mode user stories.

Static scenarios owned by a suite run via ``test_user_story_suite``.
This module keeps HTTP twins and any remaining orphan static cases.
"""

from __future__ import annotations

import pytest

from tests.stories.backend import resolve_story_backend
from tests.stories.catalog import StoryCase, iter_story_cases
from tests.stories.harness import run_story
from tests.stories.live_capability import filter_live_cases
from tests.stories.suite_catalog import is_static_suite_covered

_BACKEND = resolve_story_backend()
_CASES = [
    c
    for c in iter_story_cases(model_filter=_BACKEND.model_filter)
    if not is_static_suite_covered(c)
]
if _BACKEND.mode == "live":
    # HTTP twins + static stories that call infer/judge against real models.
    # Pure policy / recipe-shape / tool_loop stay offline (zero CI skips).
    _CASES = filter_live_cases(_CASES)


def _case_id(case: StoryCase) -> str:
    return case.label


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=_case_id)
async def test_user_story(case: StoryCase) -> None:
    await run_story(case, _BACKEND)
