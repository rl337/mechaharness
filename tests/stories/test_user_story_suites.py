"""Parametrized user-story suite runner (parallel or sequential)."""

from __future__ import annotations

import pytest

from tests.stories.backend import resolve_story_backend
from tests.stories.suite_catalog import SuiteCase, iter_suite_cases
from tests.stories.suite_harness import run_user_story_suite

_BACKEND = resolve_story_backend()
# Suites are authored under static/fixture; model_filter applies at stage resolve.
_SUITES = iter_suite_cases()


def _suite_id(case: SuiteCase) -> str:
    return case.label


@pytest.fixture(autouse=True)
def _mark_sequential_suite(request: pytest.FixtureRequest) -> None:
    """Tag sequential suites so xdist / serial runners can isolate them."""
    if "case" not in request.fixturenames:
        return
    case = request.getfixturevalue("case")
    if isinstance(case, SuiteCase) and case.suite.execution.mode == "sequential":
        request.node.add_marker(pytest.mark.serial)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _SUITES, ids=_suite_id)
async def test_user_story_suite(case: SuiteCase) -> None:
    await run_user_story_suite(case.suite, _BACKEND)
