"""Registered story harness families (``story.json`` ``kind`` values)."""

from __future__ import annotations

from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.harness.base import StoryHarness
from tests.stories.harness.cli import CliHarness
from tests.stories.harness.domains import DOMAIN_HARNESSES, KIND_TO_HARNESS_OP
from tests.stories.harness.durable_generator import DurableGeneratorHarness
from tests.stories.harness.pure_api import PURE_API_KIND_TO_OP, PureApiHarness

_PURE = PureApiHarness()
_DURABLE = DurableGeneratorHarness()
_CLI = CliHarness()

HARNESSES: dict[str, StoryHarness] = {
    _PURE.name: _PURE,
    _DURABLE.name: _DURABLE,
    _CLI.name: _CLI,
}
for _domain in DOMAIN_HARNESSES:
    if _domain.name in HARNESSES:
        raise RuntimeError(f"duplicate story harness {_domain.name!r}")
    HARNESSES[_domain.name] = _domain

# Complete legacy kind → (harness, op) map (pure_api uses renamed ops).
LEGACY_KIND_TO_HARNESS_OP: dict[str, tuple[str, str]] = dict(KIND_TO_HARNESS_OP)
for _legacy, _op in PURE_API_KIND_TO_OP.items():
    LEGACY_KIND_TO_HARNESS_OP[_legacy] = ("pure_api", _op)


def known_ops_for(kind: str) -> frozenset[str] | None:
    harness = HARNESSES.get(kind)
    if harness is None:
        return None
    return harness.known_ops()


async def run_story(case: StoryCase, backend: StoryBackend) -> None:
    meta = case.load_json("story.json")
    kind = meta["kind"]
    if backend.mode == "live" and case.adapter == "in_process":
        raise AssertionError(
            f"{case.label}: in_process stories must not be collected in live mode"
        )
    try:
        harness = HARNESSES[kind]
    except KeyError as exc:
        known = ", ".join(sorted(HARNESSES))
        raise ValueError(
            f"unknown story harness kind {kind!r} in {case.label}; known: {known}"
        ) from exc
    await harness.run(case, backend)
