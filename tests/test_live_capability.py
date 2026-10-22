"""Live story collection eligibility."""

from __future__ import annotations

from pathlib import Path

from tests.stories.catalog import StoryCase, iter_story_cases
from tests.stories.live_capability import filter_live_cases, live_eligible


def test_live_filter_keeps_http_twins_and_model_static() -> None:
    all_cases = iter_story_cases()
    live = filter_live_cases(all_cases)
    labels = {c.label for c in live}
    assert any(c.adapter == "systemone" for c in live)
    assert any(c.adapter == "openai_compat" for c in live)
    assert any(
        c.adapter == "in_process" and "fangore_jev_citation_matching_claim" in c.label
        for c in live
    )
    assert not any("tool_loop" in c.label and c.adapter == "in_process" for c in live)
    # Pure policy stories stay offline.
    assert not any("fangore_denial_equivalence" in label for label in labels)


def test_live_eligible_anthropic_static_excluded() -> None:
    root = Path("tests/fixtures/models/static/fixture/v1/stories")
    case = StoryCase(
        family="static",
        model="fixture",
        version="v1",
        story_id="nubble_anthropic_cassette_infer",
        adapter="in_process",
        root=root / "nubble_anthropic_cassette_infer",
        scenario_relpath="scenarios/cassette_infer.yaml",
    )
    assert not live_eligible(case)
