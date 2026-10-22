"""Registered story harness families (``story.json`` ``kind`` values)."""

from __future__ import annotations

from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.harness.base import StoryHarness
from tests.stories.harness.cli import CliHarness
from tests.stories.harness.domains import DOMAIN_HARNESSES, KIND_TO_HARNESS_OP
from tests.stories.harness.user_story import UserStoryHarness

_CLI = CliHarness()
_USER_STORY = UserStoryHarness()

HARNESSES: dict[str, StoryHarness] = {
    _CLI.name: _CLI,
    _USER_STORY.name: _USER_STORY,
}
for _domain in DOMAIN_HARNESSES:
    if _domain.name in HARNESSES:
        raise RuntimeError(f"duplicate story harness {_domain.name!r}")
    HARNESSES[_domain.name] = _domain

# Former kind/op inventory for migration docs (pure_api fully on CLI).
LEGACY_KIND_TO_HARNESS_OP: dict[str, tuple[str, str]] = dict(KIND_TO_HARNESS_OP)


def known_ops_for(kind: str) -> frozenset[str] | None:
    harness = HARNESSES.get(kind)
    if harness is None:
        return None
    return harness.known_ops()


async def run_story(case: StoryCase, backend: StoryBackend) -> None:
    meta = case.load_json("story.json")
    kind = meta["kind"]
    if backend.mode == "live" and case.adapter == "in_process":
        from tests.stories.live_capability import live_eligible

        if not live_eligible(case):
            raise AssertionError(
                f"{case.label}: in_process story is not live-eligible "
                "(no infer/judge verbs, or tool_loop/anthropic-only)"
            )
    try:
        harness = HARNESSES[kind]
    except KeyError as exc:
        known = ", ".join(sorted(HARNESSES))
        raise ValueError(
            f"unknown story harness kind {kind!r} in {case.label}; known: {known}"
        ) from exc
    await harness.run(case, backend)
