"""Fixture schema and twin-parity checks for user stories."""

from __future__ import annotations

from tests.stories.catalog import validate_story_fixtures


def test_story_fixtures_have_required_fields_and_twin_parity() -> None:
    errors = validate_story_fixtures()
    assert not errors, "\n".join(errors)
