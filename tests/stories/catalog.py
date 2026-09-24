"""Paths and discovery for versioned model story fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "models"


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
