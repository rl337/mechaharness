"""Legacy live entrypoint for local Qwen OpenAI-compat.

Prefer the dual-mode suite — see ``docs/guides/user-stories.md``.
``MECHA_LIVE_QWEN=1`` selects live + ``openai_compat/qwen-qwen3.6-35b-a3b``.
"""

from __future__ import annotations

import os

import pytest

from tests.stories.backend import resolve_story_backend
from tests.stories.catalog import iter_story_cases
from tests.stories.runners import run_story

pytestmark = [pytest.mark.live_qwen]


@pytest.mark.asyncio
async def test_pass_through_local_qwen_emits_events_and_cost() -> None:
    if os.environ.get("MECHA_LIVE_QWEN") != "1":
        pytest.skip("set MECHA_LIVE_QWEN=1 to hit a local Qwen server")
    os.environ.setdefault("MECHA_STORY_BACKEND", "live")
    os.environ.setdefault("MECHA_STORY_MODEL", "openai_compat/qwen-qwen3.6-35b-a3b")
    backend = resolve_story_backend()
    cases = [
        c
        for c in iter_story_cases(model_filter=backend.model_filter)
        if c.story_id == "nubble_run_cost_events"
    ]
    assert cases, "missing nubble_run_cost_events cassette for Qwen model"
    await run_story(cases[0], backend)
