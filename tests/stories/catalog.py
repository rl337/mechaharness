"""Paths and discovery for versioned model story fixtures."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "models"
REQUIRED_STORY_FIELDS = (
    "id",
    "persona",
    "title",
    "kind",
    "narrative",
    "implementation",
    "validation",
)
TWIN_PARITY_FIELDS = (
    "persona",
    "title",
    "kind",
    "narrative",
    "implementation",
    "validation",
)


@dataclass(frozen=True)
class StoryCase:
    """One (model version, story) pair under ``tests/fixtures/models``."""

    family: str
    model: str
    version: str
    story_id: str
    adapter: str
    root: Path

    @property
    def model_key(self) -> str:
        return f"{self.family}/{self.model}"

    @property
    def label(self) -> str:
        return f"{self.model_key}/{self.version}/{self.story_id}"

    def path(self, name: str) -> Path:
        return self.root / name

    def load_json(self, name: str) -> dict[str, Any]:
        return json.loads(self.path(name).read_text(encoding="utf-8"))


def iter_story_cases(*, model_filter: str | None = None) -> list[StoryCase]:
    """Walk ``family/model/version/stories/id`` trees."""
    cases: list[StoryCase] = []
    if not FIXTURES_ROOT.is_dir():
        return cases
    for manifest_path in sorted(FIXTURES_ROOT.glob("*/*/v*/manifest.json")):
        version_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        family = str(manifest["family"])
        model = str(manifest["model"])
        version = str(manifest.get("version") or version_dir.name)
        adapter = str(manifest.get("adapter") or family)
        model_key = f"{family}/{model}"
        if model_filter and model_key != model_filter and model != model_filter:
            continue
        stories_dir = version_dir / "stories"
        if not stories_dir.is_dir():
            continue
        for story_dir in sorted(p for p in stories_dir.iterdir() if p.is_dir()):
            if not (story_dir / "story.json").is_file():
                continue
            cases.append(
                StoryCase(
                    family=family,
                    model=model,
                    version=version,
                    story_id=story_dir.name,
                    adapter=adapter,
                    root=story_dir,
                )
            )
    return cases


def validate_story_payload(data: dict[str, Any], *, path: Path) -> list[str]:
    """Return human-readable errors for one ``story.json``."""
    errors: list[str] = []
    for field in REQUIRED_STORY_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path}: missing or empty required field {field!r}")
    story_id = data.get("id")
    if isinstance(story_id, str) and path.parent.name != story_id:
        errors.append(
            f"{path}: directory name {path.parent.name!r} != id {story_id!r}"
        )
    return errors


def validate_story_fixtures() -> list[str]:
    """Validate required fields and twin parity across model trees."""
    errors: list[str] = []
    by_id: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for case in iter_story_cases():
        path = case.path("story.json")
        data = case.load_json("story.json")
        errors.extend(validate_story_payload(data, path=path))
        by_id[str(data.get("id") or case.story_id)].append((path, data))

    for story_id, copies in sorted(by_id.items()):
        if len(copies) < 2:
            continue
        base = copies[0][1]
        for path, data in copies[1:]:
            for field in TWIN_PARITY_FIELDS:
                if data.get(field) != base.get(field):
                    errors.append(
                        f"twin drift for {story_id!r}: {field} differs at {path}"
                    )
    return errors
