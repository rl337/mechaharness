"""Fixture schema and twin-parity checks for user stories."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

from tests.stories.catalog import collect_canonical_stories, validate_story_fixtures
from tests.stories.suite_catalog import validate_suite_fixtures


def test_story_fixtures_have_required_fields_and_twin_parity() -> None:
    errors = validate_story_fixtures()
    assert not errors, "\n".join(errors)


def test_suite_fixtures_cover_static_stories() -> None:
    errors = validate_suite_fixtures(require_full_static_coverage=True)
    assert not errors, "\n".join(errors)


def test_story_attribution_targets_exist_in_repository() -> None:
    """Keep source attribution useful when repository documents are moved."""
    root = Path(__file__).resolve().parents[2]
    prefix = "/rl337/mechaharness/blob/main/"
    errors = []
    for story_id, story in collect_canonical_stories().items():
        for footnote in story.get("footnotes") or []:
            url = urlsplit(footnote["url"])
            if url.hostname == "github.com" and url.path.startswith(prefix):
                relative = unquote(url.path[len(prefix):])
                target = (root / relative).resolve()
                if root not in target.parents or not target.is_file():
                    errors.append(f"{story_id}: missing attribution target {relative}")
    assert not errors, "\n".join(errors)
