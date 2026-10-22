"""Fixture schema and twin-parity checks for user stories."""

from __future__ import annotations

from tests.stories.catalog import validate_story_fixtures
from tests.stories.suite_catalog import validate_suite_fixtures


def test_story_fixtures_have_required_fields_and_twin_parity() -> None:
    errors = validate_story_fixtures()
    assert not errors, "\n".join(errors)


def test_suite_fixtures_cover_static_stories() -> None:
    errors = validate_suite_fixtures(require_full_static_coverage=True)
    assert not errors, "\n".join(errors)
