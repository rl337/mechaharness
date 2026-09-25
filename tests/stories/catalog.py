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
    "footnotes",
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


def _validate_footnotes(data: dict[str, Any], *, path: Path) -> list[str]:
    errors: list[str] = []
    footnotes = data.get("footnotes")
    if footnotes is None:
        errors.append(f"{path}: missing required field 'footnotes' (use [] if none)")
        return errors
    if not isinstance(footnotes, list):
        errors.append(f"{path}: footnotes must be a list")
        return errors
    seen: set[str] = set()
    for i, item in enumerate(footnotes):
        if not isinstance(item, dict):
            errors.append(f"{path}: footnotes[{i}] must be an object")
            continue
        fid = item.get("id")
        label = item.get("label")
        url = item.get("url")
        if not isinstance(fid, str) or not fid.strip():
            errors.append(f"{path}: footnotes[{i}].id must be a non-empty string")
            continue
        if fid in seen:
            errors.append(f"{path}: duplicate footnote id {fid!r}")
        seen.add(fid)
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{path}: footnotes[{i}].label must be a non-empty string")
        if not isinstance(url, str) or not url.strip():
            errors.append(f"{path}: footnotes[{i}].url must be a non-empty string")
        note = item.get("note")
        if note is not None and not isinstance(note, str):
            errors.append(f"{path}: footnotes[{i}].note must be a string when set")
    return errors


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
    errors.extend(_validate_footnotes(data, path=path))
    return errors


def collect_canonical_stories() -> dict[str, dict[str, Any]]:
    """Return story_id -> story.json, preferring static/fixture when present."""
    by_id: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for case in iter_story_cases():
        path = case.path("story.json")
        data = case.load_json("story.json")
        by_id[str(data.get("id") or case.story_id)].append((path, data))

    canonical: dict[str, dict[str, Any]] = {}
    for story_id, copies in sorted(by_id.items()):
        preferred = next(
            (data for path, data in copies if "static/fixture" in path.as_posix()),
            copies[0][1],
        )
        canonical[story_id] = preferred
    return canonical


def validate_story_fixtures() -> list[str]:
    """Validate required fields, twin parity, and id uniqueness."""
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

    dir_to_ids: dict[str, set[str]] = defaultdict(set)
    for case in iter_story_cases():
        data = case.load_json("story.json")
        dir_to_ids[case.story_id].add(str(data.get("id") or case.story_id))
    for dirname, ids in sorted(dir_to_ids.items()):
        if len(ids) > 1:
            errors.append(
                f"directory {dirname!r} maps to multiple story ids: {sorted(ids)}"
            )

    footnote_owners: dict[str, str] = {}
    for story_id, data in collect_canonical_stories().items():
        for item in data.get("footnotes") or []:
            if not isinstance(item, dict):
                continue
            fid = item.get("id")
            if not isinstance(fid, str):
                continue
            prior = footnote_owners.get(fid)
            if prior is not None and prior != story_id:
                errors.append(
                    f"footnote id {fid!r} used by both {prior!r} and {story_id!r}"
                )
            footnote_owners[fid] = story_id

    return errors
