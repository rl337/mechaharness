"""Parametrized dual-mode user stories."""

from __future__ import annotations

import pytest

from tests.stories.backend import resolve_story_backend
from tests.stories.catalog import StoryCase, iter_story_cases
from tests.stories.runners import run_story

_BACKEND = resolve_story_backend()
_CASES = iter_story_cases(model_filter=_BACKEND.model_filter)


def _case_id(case: StoryCase) -> str:
    return case.label


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=_case_id)
async def test_user_story(case: StoryCase) -> None:
    await run_story(case, _BACKEND)
